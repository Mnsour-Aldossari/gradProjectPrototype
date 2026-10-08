"""What px4_link works out, apart from ROS: PX4's mode names, distances, and whether what PX4 says over uXRCE-DDS
agrees with what the backend says from MAVLink."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from .core import EARTH_RADIUS_M, FINISHED

# PX4's vehicle_status.nav_state (px4_msgs/msg/VehicleStatus.msg, PX4 v1.17).
NAV_STATES = {
    0: "manual", 1: "altctl", 2: "posctl", 3: "auto_mission", 4: "auto_loiter", 5: "auto_rtl", 6: "position_slow",
    8: "altitude_cruise", 10: "acro", 12: "descend", 13: "termination", 14: "offboard", 15: "stab",
    17: "auto_takeoff", 18: "auto_land", 19: "auto_follow_target", 20: "auto_precland", 21: "orbit",
    22: "auto_vtol_takeoff",
}  # fmt: skip
ARMING_STATE_ARMED = 2
TRACK_KEPT_S = 10.0  # PX4 positions kept to compare with the backend's, which arrive later
AGREE_M = 1.0  # within this, the two positions are the same


def nav_state_name(nav_state: int) -> str:
    return NAV_STATES.get(nav_state, f"mode_{nav_state}")


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Across the ground, as the survey frame measures it (fine over a survey area)."""
    x = math.radians(lon2 - lon1) * EARTH_RADIUS_M * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1) * EARTH_RADIUS_M
    return math.hypot(x, y)


@dataclass(frozen=True)
class Fix:
    t: float  # seconds, any clock that only goes forward
    lat: float
    lon: float
    alt_m: float


class Track:
    """PX4's last positions. The backend's latest one is a little older than PX4's (it goes through MAVLink, the
    mission runner and a REST poll), so it is compared with the track PX4 flew over the last seconds, not with
    PX4's position now: the same vehicle's position lies on that track."""

    def __init__(self, kept_s: float = TRACK_KEPT_S) -> None:
        self._kept_s = kept_s
        self._fixes: deque[Fix] = deque()

    def add(self, fix: Fix) -> None:
        self._fixes.append(fix)
        while self._fixes and fix.t - self._fixes[0].t > self._kept_s:
            self._fixes.popleft()

    @property
    def latest(self) -> Fix | None:
        return self._fixes[-1] if self._fixes else None

    def distance_m(self, lat: float, lon: float) -> float | None:
        """From (lat, lon) to the nearest point of the track (its segments), None without a position."""
        fixes = list(self._fixes)
        if not fixes:
            return None
        if len(fixes) == 1:
            return distance_m(fixes[0].lat, fixes[0].lon, lat, lon)
        best = math.inf
        for a, b in zip(fixes, fixes[1:]):
            best = min(best, _to_segment_m(lat, lon, a, b))
        return best


def _to_segment_m(lat: float, lon: float, a: Fix, b: Fix) -> float:
    k = math.radians(1) * EARTH_RADIUS_M
    c = math.cos(math.radians(lat))
    ax, ay = (a.lon - lon) * k * c, (a.lat - lat) * k
    bx, by = (b.lon - lon) * k * c, (b.lat - lat) * k
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    s = 0.0 if length2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length2))
    return math.hypot(ax + s * dx, ay + s * dy)


def backend_flight(mission: dict | None) -> str:
    """What the backend says of the UAV: "flying", "down" or "" (it cannot tell: landing, or no mission)."""
    if not mission:
        return ""
    if mission.get("status") in FINISHED:
        return "down"
    if mission.get("status") == "running" and mission.get("phase") in ("surveying", "paused", "returning"):
        return "flying"
    return ""


@dataclass(frozen=True)
class Comparison:
    ok: bool
    warn: bool  # not ok, but may pass (taking off, landing, the backend not yet up to date)
    message: str
    values: dict


def compare(track: Track, landed: bool | None, mission: dict | None, backend_fix: dict | None) -> Comparison:
    """PX4 over uXRCE-DDS against the backend over MAVLink. backend_fix: the backend's latest telemetry point."""
    values: dict = {"mission": mission["id"] if mission else "none"}
    if track.latest is None:
        return Comparison(False, False, "No position from PX4 (is the agent running, and PX4?)", values)
    if not mission or backend_fix is None:
        return Comparison(True, False, "PX4 read; no PX4 mission in the backend to compare with", values)
    gap = track.distance_m(backend_fix["lat"], backend_fix["lon"])
    values["position_difference_m"] = round(gap, 2)
    values["altitude_difference_m"] = round(abs(track.latest.alt_m - backend_fix["alt_msl_m"]), 2)
    flight = backend_flight(mission)
    values["backend_says"] = flight or "unknown"
    values["px4_says"] = "unknown" if landed is None else ("down" if landed else "flying")
    problems = []
    if gap > AGREE_M:
        problems.append(f"positions {gap:.1f} m apart")
    if flight and landed is not None and (flight == "down") != landed:
        problems.append(f"the backend says {flight}, PX4 says {values['px4_says']}")
    if problems:
        return Comparison(False, True, "; ".join(problems), values)
    return Comparison(True, False, f"PX4 and the backend agree (within {gap:.2f} m)", values)
