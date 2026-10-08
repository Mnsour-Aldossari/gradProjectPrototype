"""Starting and commanding missions through the backend (control_core), against a fake backend."""

import pytest

from uav_landmine_ros.backend_client import Backend, BackendError, credentials
from uav_landmine_ros.control_core import START_TIMEOUT_S, ControlCore


class FakeBackend:
    def __init__(self, replies=None, missions=(), mission=None, detections=()):
        self.replies = replies or {}
        self.posts = []
        self._missions, self._mission, self._detections = list(missions), mission, list(detections)

    def post(self, path, body=None, timeout_s=None):
        self.posts.append((path, body, timeout_s))
        return self.replies.get(path, (404, "Mission not found"))

    def missions(self):
        return self._missions

    def mission(self, mission_id):
        return self._mission

    def detections(self, mission_id, method="adaptive"):
        return self._detections


def test_the_demo_starts_with_the_simulator_only():
    backend = FakeBackend({"/api/missions/demo": (202, {"id": 7, "uav_source": "simulated"})})
    answer = ControlCore(backend).start(0, speed_factor=20)
    assert (answer.accepted, answer.mission_id) == (True, 7)
    assert backend.posts == [("/api/missions/demo", {"speed_factor": 20}, None)]
    refused = ControlCore(backend).start(0, uav_source="px4")
    assert not refused.accepted and "simulator" in refused.message
    assert len(backend.posts) == 1  # nothing was sent


def test_a_planned_mission_starts_with_what_flies_it_and_px4_gets_time():
    backend = FakeBackend({"/api/missions/3/start": (202, {"id": 3, "uav_source": "px4"})})
    answer = ControlCore(backend).start(3, "px4", -1.0, gazebo=True)
    assert answer.accepted and "px4" in answer.message
    assert backend.posts == [("/api/missions/3/start", {"uav_source": "px4", "gazebo": True}, START_TIMEOUT_S)]


def test_the_backends_refusal_is_passed_on():
    backend = FakeBackend({"/api/missions/3/start": (403, "Only a mission supervisor can do this")})
    answer = ControlCore(backend).start(3)
    assert not answer.accepted and answer.message == "Only a mission supervisor can do this (403)"


def test_commands_go_to_the_mission_flying():
    backend = FakeBackend(
        {"/api/missions/9/control": (202, {"phase": "paused"})},
        missions=[{"id": 4, "status": "completed"}, {"id": 9, "status": "running"}],
    )
    answer = ControlCore(backend).control(0, "pause")
    assert (answer.accepted, answer.mission_id, answer.phase) == (True, 9, "paused")
    assert backend.posts == [("/api/missions/9/control", {"action": "pause"}, None)]


def test_unknown_commands_and_no_mission_flying_are_refused_without_asking():
    backend = FakeBackend(missions=[{"id": 4, "status": "completed"}])
    assert not ControlCore(backend).control(4, "takeoff").accepted
    nothing = ControlCore(backend).control(0, "land")
    assert not nothing.accepted and nothing.message == "No mission is flying"
    assert backend.posts == []


def test_progress_counts_the_detections_by_category():
    mission = {"status": "running", "phase": "surveying", "progress": 0.4, "stats": {"sensor_readings": 812},
               "error": None, "sensor_collection": None, "sensor_coverage": None}  # fmt: skip
    detections = [{"category": "high"}, {"category": "suspect"}, {"category": "clutter"}, {"category": "clutter"}]
    p = ControlCore(FakeBackend(mission=mission, detections=detections)).progress(5)
    assert (p.status, p.phase, p.readings, p.high, p.suspect, p.clutter) == ("running", "surveying", 812, 1, 1, 2)
    assert (p.sensor_coverage, p.finished) == (-1.0, False)


def test_a_token_from_the_dashboard_stands_for_a_password(monkeypatch):
    monkeypatch.setenv("UAV_CONTROL_TOKEN", "abc.def")
    monkeypatch.setenv("UAV_CONTROL_PASSWORD", "unused")
    assert credentials("UAV_CONTROL") == ("", "", "abc.def")
    backend = Backend("http://127.0.0.1:8000", *credentials("UAV_CONTROL"))
    with pytest.raises(BackendError, match="start ROS 2 again"):
        backend._sign_in()  # an expired token: no password to sign in with again
    monkeypatch.delenv("UAV_CONTROL_TOKEN")
    monkeypatch.setenv("UAV_CONTROL_USERNAME", "supervisor")
    assert credentials("UAV_CONTROL") == ("supervisor", "unused", "")
