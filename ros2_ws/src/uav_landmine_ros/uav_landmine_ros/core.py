"""The parts of the nodes that need no ROS: the survey frame, the backend's detector fed reading by reading, and
the mission as the backend sends it. Kept apart so they can be tested without a ROS graph."""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path

EARTH_RADIUS_M = 6_371_008.8  # as backend/app/simulation/geo.py
SAMPLE_PERIOD_S = 0.2  # time between readings: the simulator's step and the PX4 source's frame period
DETECT_EVERY = 25  # readings between two runs of the detector: 5 s of flight, as the mission runner does


def backend_source() -> Path:
    """The backend folder whose app.detection the detector node runs: UAV_BACKEND_SRC, else the checkout this
    package was built from (the workspace links to it)."""
    if os.environ.get("UAV_BACKEND_SRC"):
        return Path(os.environ["UAV_BACKEND_SRC"])
    for parent in Path(__file__).resolve().parents:
        if (parent / "backend" / "app" / "detection" / "__init__.py").is_file():
            return parent / "backend"
    raise RuntimeError("backend/app/detection not found; set UAV_BACKEND_SRC to the project's backend folder")


def import_detection():
    """The project's detection library. It needs nothing but the standard library (the backend's tests check that),
    so it runs here as it is, without FastAPI or a database."""
    path = str(backend_source())
    if path not in sys.path:
        sys.path.insert(0, path)
    import app.detection as detection

    return detection


@dataclass(frozen=True)
class SurveyFrame:
    """Metres east (x) and north (y) of the centre of the survey area: the backend's LocalFrame, same arithmetic."""

    lat0: float
    lon0: float

    @classmethod
    def centred_on(cls, area: list[list[float]]) -> SurveyFrame:
        lats = [p[0] for p in area]
        lons = [p[1] for p in area]
        return cls(sum(lats) / len(lats), sum(lons) / len(lons))

    def to_xy(self, lat: float, lon: float) -> tuple[float, float]:
        x = math.radians(lon - self.lon0) * EARTH_RADIUS_M * math.cos(math.radians(self.lat0))
        y = math.radians(lat - self.lat0) * EARTH_RADIUS_M
        return x, y

    def to_latlon(self, x: float, y: float) -> tuple[float, float]:
        lat = self.lat0 + math.degrees(y / EARTH_RADIUS_M)
        lon = self.lon0 + math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(self.lat0))))
        return lat, lon


FINISHED = ("completed", "stopped", "failed")


@dataclass(frozen=True)
class MissionParams:
    """What the detector needs from a mission (GET /api/missions/{id})."""

    id: int
    soil_type: str
    altitude_m: float
    speed_mps: float
    line_spacing_m: float
    area: tuple[tuple[float, float], ...]
    sample_period_s: float = SAMPLE_PERIOD_S

    @classmethod
    def from_json(cls, mission: dict) -> MissionParams:
        return cls(
            id=mission["id"],
            soil_type=mission["soil_type"],
            altitude_m=mission["altitude_m"],
            speed_mps=mission["speed_mps"],
            line_spacing_m=mission["line_spacing_m"],
            area=tuple((p[0], p[1]) for p in mission["area"]),
        )

    @property
    def frame(self) -> SurveyFrame:
        return SurveyFrame.centred_on([list(p) for p in self.area])


@dataclass(frozen=True)
class Found:
    """A candidate of the detector node, with where it is."""

    category: str
    confidence: float
    latitude: float
    longitude: float
    x_m: float
    y_m: float
    peak_md: float
    peak_gpr: float
    est_depth_m: float | None
    n_hits: int
    explanation: str


class DetectorCore:
    """The backend's adaptive detector, fed the readings one by one in the order they were taken, as the mission
    runner feeds it. Every output is a potential detection for trained personnel to verify."""

    def __init__(self, mission: MissionParams, detect_every: int = DETECT_EVERY) -> None:
        detection = import_detection()
        self._reading = detection.Reading
        self.mission = mission
        self.frame = mission.frame
        context = detection.SurveyContext(
            mission.soil_type, mission.altitude_m, mission.speed_mps, mission.line_spacing_m, mission.sample_period_s
        )
        self._detector = detection.live_detector(context)  # the one the mission runner uses
        self._pending: list = []
        self._detect_every = detect_every
        self.readings = 0
        self.last_id = 0

    def add(self, reading_id: int, t_s: float, x_m: float, y_m: float, height_m: float, md: float, gpr_amp: float,
            gpr_twt_ns: float) -> bool:  # fmt: skip
        """Takes one reading; True when it is time to look again. Readings already taken are ignored."""
        if reading_id <= self.last_id:
            return False
        self.last_id = reading_id
        self._pending.append(self._reading(t_s, x_m, y_m, height_m, md, gpr_amp, gpr_twt_ns))
        self.readings += 1
        return len(self._pending) >= self._detect_every

    def found(self) -> list[Found]:
        self._detector.add(self._pending)
        self._pending = []
        out = []
        for c in self._detector.candidates():
            lat, lon = self.frame.to_latlon(c.x, c.y)
            out.append(
                Found(c.category.value, c.confidence, lat, lon, c.x, c.y, c.peak_md, c.peak_gpr, c.est_depth_m,
                      c.n_hits, c.explanation)
            )  # fmt: skip
        return out


def rounded(category: str, confidence: float, n_hits: int, latitude: float, longitude: float) -> tuple:
    """A detection as the backend stores it (runner._apply rounds the score to 3 places), for comparing."""
    return category, n_hits, round(confidence, 3), latitude, longitude
