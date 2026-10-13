"""Starting and commanding missions through the backend, without ROS (control.py wraps it in a node).

The backend stays the owner of the flight: it sends the commands on to the simulator or to PX4, confirms the
landing and records the sensor collection, so the dashboard and ROS always show the same mission.
"""

from __future__ import annotations

from dataclasses import dataclass

from .core import FINISHED

ACTIONS = ("pause", "resume", "return", "land")
START_TIMEOUT_S = 300.0  # a start with PX4 waits for PX4 SITL to be ready at the takeoff point


@dataclass(frozen=True)
class Answer:
    accepted: bool
    mission_id: int
    message: str
    phase: str = ""


@dataclass(frozen=True)
class Progress:
    mission_id: int
    status: str
    phase: str
    progress: float
    readings: int
    high: int
    suspect: int
    clutter: int
    error: str
    sensor_collection: str
    sensor_coverage: float  # -1: not known

    @property
    def finished(self) -> bool:
        return self.status in FINISHED


class ControlCore:
    def __init__(self, backend) -> None:
        self.backend = backend

    def start(self, mission_id: int, uav_source: str = "", speed_factor: float = -1.0, gazebo: bool = False) -> Answer:
        """mission_id 0: the demo scenario (always the simulator)."""
        body: dict = {} if speed_factor < 0 else {"speed_factor": speed_factor}
        if mission_id == 0:
            if uav_source not in ("", "simulated") or gazebo:
                return Answer(False, 0, "The demo scenario flies with the simulator only")
            code, reply = self.backend.post("/api/missions/demo", body or None)
        else:
            body |= {"uav_source": uav_source or "simulated", "gazebo": gazebo}
            code, reply = self.backend.post(f"/api/missions/{mission_id}/start", body, START_TIMEOUT_S)
        if code == 202:
            return Answer(True, reply["id"], f"Mission {reply['id']} started ({reply['uav_source']})")
        return Answer(False, mission_id, f"{reply} ({code})")

    def flying(self) -> int | None:
        """The newest mission that is flying."""
        running = [m["id"] for m in self.backend.missions() if m["status"] == "running"]
        return max(running) if running else None

    def control(self, mission_id: int, action: str) -> Answer:
        """mission_id 0: the mission that is flying."""
        if action not in ACTIONS:
            return Answer(False, mission_id, f"Unknown action {action!r}: pause, resume, return or land")
        if mission_id == 0:
            mission_id = self.flying() or 0
            if not mission_id:
                return Answer(False, 0, "No mission is flying")
        code, reply = self.backend.post(f"/api/missions/{mission_id}/control", {"action": action})
        if code == 202:
            return Answer(True, mission_id, f"{action.capitalize()} accepted", reply.get("phase") or "")
        return Answer(False, mission_id, f"{reply} ({code})")

    def progress(self, mission_id: int) -> Progress:
        m = self.backend.mission(mission_id)
        counts = {"high": 0, "suspect": 0, "clutter": 0}
        for d in self.backend.detections(mission_id):
            counts[d["category"]] = counts.get(d["category"], 0) + 1
        coverage = m.get("sensor_coverage")
        return Progress(
            mission_id=mission_id,
            status=m["status"],
            phase=m.get("phase") or "",
            progress=float(m["progress"]),
            readings=int((m.get("stats") or {}).get("sensor_readings", 0)),
            high=counts["high"],
            suspect=counts["suspect"],
            clutter=counts["clutter"],
            error=m.get("error") or "",
            sensor_collection=m.get("sensor_collection") or "",
            sensor_coverage=-1.0 if coverage is None else float(coverage),
        )
