"""A mission is completed only once the UAV is confirmed on the ground (landing.py), and its sensor collection is
reported apart from the flight (api/collection.py): a flight can end well with readings missing, and missing
readings never stop a flight."""

from __future__ import annotations

import asyncio
import dataclasses
import math

import pytest
from conftest import auth_headers, mission_body, wait_until_finished
from sqlmodel import Session

from app.api.collection import COMPLETE, FAILED, NOT_STARTED, PARTIAL, assess, lane_coverage
from app.db import make_engine
from app.models import Mission, SensorReading
from app.seed import fail_interrupted_missions
from app.uav import SimulatedSource
from app.uav.control import FlightControl
from app.uav.landing import landing_problems
from app.uav.simulated_source import LANDED
from app.uav.source import BatteryStatus, GlobalPositionInt, MissionCurrent, TelemetryFrame, VehicleStatus


def frame(height_m: float = 0.0, **status) -> TelemetryFrame:
    return TelemetryFrame(
        position=GlobalPositionInt(0, 0, 0, 0, round(height_m * 1000), 0, 0, 0, 0),
        battery=BatteryStatus(80),
        mission=MissionCurrent(10, 10),
        sensor=None,
        progress=1.0,
        status=dataclasses.replace(LANDED, **status),
    )


# The landing rule


def test_a_landing_is_confirmed_disarmed_on_the_ground_recent_and_without_failsafe():
    assert landing_problems(frame(0.2), age_s=0.5) == []


@pytest.mark.parametrize(
    ("last", "age_s", "problem"),
    [
        (frame(armed=True), 0.0, "still armed"),
        (frame(landed_state=2), 0.0, "not reported on the ground"),
        (frame(1.2), 0.0, "1.20 m above the ground"),
        (frame(), 2.5, "the last telemetry is 2.5 s old"),
        (frame(age_s=1.5), 0.7, "the last telemetry is 2.2 s old"),
        (frame(age_s=math.inf), 0.0, "no telemetry on whether it is armed and on the ground"),
        (frame(failsafe="Failsafe activated: battery low"), 0.0, "failsafe: Failsafe activated: battery low"),
        (dataclasses.replace(frame(), status=None), 0.0, "the UAV did not report whether it is armed or on the ground"),
        (None, 0.0, "no telemetry from the UAV"),
    ],
)
def test_a_landing_is_not_confirmed(last, age_s, problem):
    assert problem in landing_problems(last, age_s)


# Sensor coverage of the lanes

LANES = [(0.0, 0.0), (10.0, 0.0), (10.0, 2.0), (0.0, 2.0)]  # two 10 m lanes, east then west


def along(y: float, xs) -> list[tuple[float, float]]:
    return [(x, y) for x in xs]


def test_lanes_read_every_0_4_m_are_fully_covered():
    points = along(0.0, [i * 0.4 for i in range(26)]) + along(2.0, [10 - i * 0.4 for i in range(26)])
    coverage, gaps = lane_coverage(LANES, points, gap_m=1.2)
    assert (coverage, gaps) == (pytest.approx(1.0), [])


def test_a_stretch_without_readings_is_a_gap_on_its_lane():
    readings = [i * 0.4 for i in range(26) if not 4.0 < i * 0.4 < 9.0]  # nothing between 4 and 9 m on lane 2
    coverage, gaps = lane_coverage(LANES, along(0.0, [i * 0.4 for i in range(26)]) + along(2.0, readings), 1.2)
    assert [lane for lane, _ in gaps] == [2]
    assert gaps[0][1] == pytest.approx(5.2)
    assert coverage == pytest.approx(14.8 / 20)


def test_pieces_of_one_lane_count_apart():
    """A concave outline cuts a lane into pieces with the same y: each reading goes to the piece it lies on."""
    lanes = [(0.0, 0.0), (4.0, 0.0), (6.0, 0.0), (10.0, 0.0)]
    coverage, gaps = lane_coverage(lanes, along(0.0, [i * 0.4 for i in range(11)]), gap_m=1.2)
    assert ([lane for lane, _ in gaps], coverage) == ([2], 0.5)


def test_collection_complete_partial_failed_or_not_started():
    full = along(0.0, [i * 0.4 for i in range(26)]) + along(2.0, [10 - i * 0.4 for i in range(26)])
    done = assess(LANES, full, flew=True, sample_spacing_m=0.4)
    assert (done.status, done.readings, done.coverage, done.note) == (COMPLETE, 52, 1.0, None)

    early = assess(LANES, full[:26], flew=True, sample_spacing_m=0.4, ended="Ended early (landed by the supervisor)")
    assert (early.status, early.coverage, early.note) == (PARTIAL, 0.5, "Ended early (landed by the supervisor)")

    paused = assess(LANES, full, flew=True, sample_spacing_m=0.4, longest_pause_s=75)
    assert paused.status == PARTIAL
    assert paused.note == "Paused for 1 min 15 s (over 1 min 0 s): the lanes were not read in one go"

    nothing = assess(LANES, [], flew=True, sample_spacing_m=0.4)
    assert (nothing.status, nothing.readings, nothing.note) == (FAILED, 0, "No sensor readings were received")
    assert assess(LANES, [], flew=False, sample_spacing_m=0.4).status == NOT_STARTED


def test_the_longest_pause_is_measured_in_real_time():
    now = [0.0]
    control = FlightControl(clock=lambda: now[0])
    control.request("pause")
    now[0] = 30.0
    control.request("resume")
    control.request("pause")
    now[0] = 100.0
    assert control.longest_pause_s == 70.0  # the pause under way counts too
    control.request("land")
    now[0] = 500.0
    assert control.longest_pause_s == 70.0


# Whole missions through the API, the simulator changed where needed


def fly(client, monkeypatch, source_cls=None) -> dict:
    if source_cls is not None:
        monkeypatch.setattr("app.api.runner.SimulatedSource", source_cls)
    headers = auth_headers(client, "admin")
    mission_id = client.post("/api/missions", json=mission_body(), headers=headers).json()["id"]
    assert client.get(f"/api/missions/{mission_id}", headers=headers).json()["sensor_collection"] == NOT_STARTED
    r = client.post(f"/api/missions/{mission_id}/start", json={"speed_factor": 0}, headers=headers)
    assert r.status_code == 202, r.text
    return wait_until_finished(client, mission_id, headers)


def changed(change):
    """The simulator with each frame passed through change(index, frame), which returns the frame to send."""

    class Changed(SimulatedSource):
        async def frames(self):
            i = 0
            async for f in super().frames():
                yield change(i, f, self)
                i += 1

    return Changed


def test_a_simulated_survey_lands_and_reads_every_lane(client, monkeypatch):
    mission = fly(client, monkeypatch)
    assert (mission["status"], mission["error"]) == ("completed", None)
    assert (mission["sensor_collection"], mission["sensor_coverage"], mission["sensor_note"]) == (COMPLETE, 1.0, None)
    assert mission["sensor_reading_count"] == mission["stats"]["sensor_readings"] > 0


def test_a_uav_that_stays_armed_fails_the_mission_but_its_readings_stay_complete(client, monkeypatch):
    stays_armed = changed(lambda i, f, _: dataclasses.replace(f, status=dataclasses.replace(f.status, armed=True)))
    mission = fly(client, monkeypatch, stays_armed)
    assert (mission["status"], mission["error"]) == ("failed", "Landing not confirmed: still armed")
    assert mission["sensor_collection"] == COMPLETE


def test_a_uav_still_in_the_air_with_a_failsafe_fails_with_each_reason(client, monkeypatch):
    def up_there(i, f, _):
        p = dataclasses.replace(f.position, relative_alt=1400)
        return dataclasses.replace(f, position=p, status=VehicleStatus(True, 2, "Failsafe activated: battery low"))

    mission = fly(client, monkeypatch, changed(up_there))
    assert mission["status"] == "failed"
    assert mission["error"] == (
        "Landing not confirmed: still armed; not reported on the ground; 1.40 m above the ground; "
        "failsafe: Failsafe activated: battery low"
    )


def test_old_telemetry_does_not_confirm_a_landing(client, monkeypatch):
    class SilentAtTheEnd(SimulatedSource):
        async def frames(self):
            async for f in super().frames():
                yield f
            await asyncio.sleep(2.1)  # the link goes quiet before the run ends

    mission = fly(client, monkeypatch, SilentAtTheEnd)
    assert mission["status"] == "failed"
    assert mission["error"].startswith("Landing not confirmed: the last telemetry is 2.")


def test_return_home_stops_the_mission_with_a_partial_collection(client, monkeypatch):
    def return_at_300(i, f, source):
        if i == 300:
            source.control.request("return")
        return f

    mission = fly(client, monkeypatch, changed(return_at_300))
    assert (mission["status"], mission["error"]) == ("stopped", "Returned home by the supervisor")
    assert mission["sensor_collection"] == PARTIAL
    assert mission["sensor_note"] == "Ended early (returned home by the supervisor)"
    assert 0 < mission["sensor_coverage"] < 0.5


def test_return_home_before_takeoff_stops_the_mission_on_the_ground(client, monkeypatch):
    """The command can come before the first frame (the run is still reading the mission): the UAV never took off."""

    class ReturnedAtOnce(SimulatedSource):
        async def frames(self):
            self.control.request("return")
            async for f in super().frames():
                yield f

    mission = fly(client, monkeypatch, ReturnedAtOnce)
    assert (mission["status"], mission["error"]) == ("stopped", "Returned home by the supervisor")
    assert (mission["sensor_collection"], mission["sensor_reading_count"]) == (NOT_STARTED, 0)


def test_return_home_without_a_confirmed_landing_fails(client, monkeypatch):
    def return_then_stay_armed(i, f, source):
        if i == 300:
            source.control.request("return")
        return dataclasses.replace(f, status=dataclasses.replace(f.status, armed=True))

    mission = fly(client, monkeypatch, changed(return_then_stay_armed))
    assert mission["status"] == "failed"
    assert mission["error"] == "Returned home by the supervisor, but the landing was not confirmed: still armed"


def test_a_sensor_that_drops_out_leaves_a_gap_but_the_flight_completes(client, monkeypatch):
    silent = changed(lambda i, f, _: dataclasses.replace(f, sensor=None) if 200 <= i < 240 else f)
    mission = fly(client, monkeypatch, silent)
    assert (mission["status"], mission["error"]) == ("completed", None)
    assert mission["sensor_collection"] == PARTIAL
    assert mission["sensor_note"].startswith("Gaps in the readings on lane")
    assert 0.9 < mission["sensor_coverage"] < 1.0


def test_no_readings_at_all_fail_the_collection_not_the_flight(client, monkeypatch):
    mission = fly(client, monkeypatch, changed(lambda i, f, _: dataclasses.replace(f, sensor=None)))
    assert mission["status"] == "completed"
    assert (mission["sensor_collection"], mission["sensor_reading_count"]) == (FAILED, 0)


def test_a_flight_that_fails_keeps_and_counts_what_was_read(client, monkeypatch):
    class Breaks(SimulatedSource):
        async def frames(self):
            i = 0
            async for f in super().frames():
                if i == 333:
                    raise RuntimeError("Lost the link to PX4")
                yield f
                i += 1

    mission = fly(client, monkeypatch, Breaks)
    assert (mission["status"], mission["error"]) == ("failed", "RuntimeError: Lost the link to PX4")
    assert (mission["sensor_collection"], mission["sensor_note"]) == (PARTIAL, "The flight failed before the last lane")
    # Every reading taken before the failure is stored, and counted.
    assert mission["sensor_reading_count"] == mission["stats"]["sensor_readings"] == 333


def test_a_mission_cut_off_by_a_server_stop_is_assessed_from_its_stored_readings(client, database_url):
    headers = auth_headers(client, "admin")
    mission_id = client.post("/api/missions", json=mission_body(), headers=headers).json()["id"]
    engine = make_engine(database_url)
    with Session(engine) as session:
        mission = session.get(Mission, mission_id)
        mission.status, mission.progress = "running", 0.1
        lat, lon = mission.path[0]
        session.add(SensorReading(mission_id=mission_id, t_s=0, lat=lat, lon=lon, relative_alt_m=1.5, md=0.1,
                                  gpr_amp=0.1, gpr_twt_ns=3))
        session.add(mission)
        session.commit()
    fail_interrupted_missions(engine)
    engine.dispose()
    mission = client.get(f"/api/missions/{mission_id}", headers=headers).json()
    assert (mission["status"], mission["error"]) == ("failed", "Interrupted by a server restart")
    assert (mission["sensor_collection"], mission["sensor_reading_count"]) == (PARTIAL, 1)
    assert mission["sensor_note"] == "The server stopped before the last lane"
