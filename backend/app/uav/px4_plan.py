"""The parts of the PX4 source that need no vehicle: the mission PX4 is given, progress along the survey path, and
`TelemetryFrame`s built from PX4's telemetry. Kept apart from MAVSDK so they are tested without PX4 running."""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.simulation import Simulation, SurveyPlan
from app.simulation.geo import LocalFrame

from .source import BatteryStatus, GlobalPositionInt, MissionCurrent, SensorSample, TelemetryFrame

# PX4 refuses a mission whose first waypoint is further than MIS_DIST_1WP from home (900 m by default).
MAX_HOME_DISTANCE_M = 900.0
# PX4's default acceptance radius (NAV_ACC_RAD, 2 m) is as wide as the gap between survey lanes.
ACCEPTANCE_RADIUS_M = 0.5


@dataclass(frozen=True)
class Waypoint:
    lat: float
    lon: float
    relative_alt_m: float
    speed_m_s: float


def survey_waypoints(sim: Simulation) -> list[Waypoint]:
    """The lawnmower path the simulator flies, as waypoints at the mission's height and speed."""
    cfg = sim.config
    return [Waypoint(lat, lon, cfg.altitude_m, cfg.speed_mps) for lat, lon in sim.plan.waypoints_latlon]


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Ground distance between two lat/lon points, accurate over the few kilometres that matter here."""
    return math.dist((0.0, 0.0), LocalFrame(*a).to_xy(*b))


def home_check(home: tuple[float, float], waypoints: list[Waypoint]) -> str | None:
    """A reason PX4 would refuse the mission from this home position, or None."""
    d = distance_m(home, (waypoints[0].lat, waypoints[0].lon))
    if d <= MAX_HOME_DISTANCE_M:
        return None
    return (
        f"The survey area is {d / 1000:.1f} km from the PX4 home position; PX4 accepts up to "
        f"{MAX_HOME_DISTANCE_M:.0f} m. Restart PX4 with PX4_HOME_LAT and PX4_HOME_LON at the area."
    )


class PathProgress:
    """Fraction of the survey path flown, from the vehicle position and the waypoint it is flying to."""

    def __init__(self, plan: SurveyPlan) -> None:
        self._points = plan.waypoints_xy
        self._starts = [0.0]
        for a, b in zip(self._points, self._points[1:]):
            self._starts.append(self._starts[-1] + math.dist(a, b))
        self._total = self._starts[-1]

    def fraction(self, x: float, y: float, target: int) -> float:
        # target 0: still on the way to the first waypoint, where the survey starts.
        if target <= 0 or self._total <= 0:
            return 0.0
        if target >= len(self._points):
            return 1.0
        (x0, y0), (x1, y1) = self._points[target - 1], self._points[target]
        length = math.dist((x0, y0), (x1, y1))
        u = 0.0 if length == 0 else ((x - x0) * (x1 - x0) + (y - y0) * (y1 - y0)) / length**2
        along = self._starts[target - 1] + min(1.0, max(0.0, u)) * length
        return along / self._total


@dataclass(frozen=True)
class Px4State:
    """The latest values PX4 reported, one per telemetry stream."""

    lat_deg: float
    lon_deg: float
    absolute_alt_m: float
    relative_alt_m: float
    v_north_m_s: float
    v_east_m_s: float
    v_down_m_s: float
    heading_deg: float
    battery_pct: float
    current: int  # mission item being flown to (MAVSDK MissionProgress.current)
    total: int


def surveying(state: Px4State) -> bool:
    """On the survey lines: past the first waypoint and not yet finished. Takeoff and the way home carry no
    sensor readings, as the payload would not be scanning there."""
    return 1 <= state.current < state.total


def build_frame(state: Px4State, t_s: float, sim: Simulation, progress: PathProgress) -> TelemetryFrame:
    x, y = sim.frame.to_xy(state.lat_deg, state.lon_deg)
    sensor = None
    if surveying(state):
        # MD and GPR are not MAVLink data: the project's sensor model reads the buried objects at PX4's position.
        s = sim.sensor_sample(x, y, state.relative_alt_m)
        sensor = SensorSample(md=s.md, gpr_amp=s.gpr_amp, gpr_twt_ns=s.gpr_twt_ns)
    return TelemetryFrame(
        position=GlobalPositionInt(
            time_boot_ms=round(t_s * 1000),
            lat=round(state.lat_deg * 1e7),
            lon=round(state.lon_deg * 1e7),
            alt=round(state.absolute_alt_m * 1000),
            relative_alt=round(state.relative_alt_m * 1000),
            vx=round(state.v_north_m_s * 100),
            vy=round(state.v_east_m_s * 100),
            vz=round(state.v_down_m_s * 100),
            hdg=round(state.heading_deg * 100) % 36000,
        ),
        battery=BatteryStatus(battery_remaining=round(state.battery_pct)),
        mission=MissionCurrent(seq=state.current, total=state.total),
        sensor=sensor,
        progress=progress.fraction(x, y, state.current),
    )
