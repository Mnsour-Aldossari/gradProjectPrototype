"""The supervisor's flight commands: pause, resume, return home and land, with the simulator."""

from __future__ import annotations

import asyncio
import math

import pytest
from conftest import auth_headers, mission_body, wait_until_finished

from app.simulation import DEMO_AREA, SimulationConfig, build_simulation
from app.uav import SimulatedSource
from app.uav.control import ControlRejected, FlightControl

CONFIG = SimulationConfig(
    area=DEMO_AREA, altitude_m=1.5, speed_mps=3.0, line_spacing_m=2.5, soil_type="dry_sand", seed=11
)


def test_commands_that_do_not_apply_are_refused():
    control = FlightControl()
    with pytest.raises(ControlRejected, match="not paused"):
        control.request("resume")
    assert control.request("pause") == "paused" and not control.scanning
    with pytest.raises(ControlRejected, match="already paused"):
        control.request("pause")
    assert control.request("return") == "returning"  # straight from a pause
    assert control.stop_reason == "Returned home by the supervisor"
    for action in ("pause", "resume", "land", "return"):
        with pytest.raises(ControlRejected, match="already returning"):
            control.request(action)


async def _fly(command_at: dict[int, str]) -> list:
    """Frames from the simulator, giving a command after the given frame numbers."""
    source = SimulatedSource(CONFIG, speed_factor=0)
    source.control = FlightControl()
    frames = []
    async for f in source.frames():
        frames.append(f)
        if (action := command_at.get(len(frames))) is not None:
            source.control.request(action)
    return frames


def test_pause_holds_the_flight_until_resumed():
    async def run():
        source = SimulatedSource(CONFIG, speed_factor=0)
        control = source.control = FlightControl()
        frames = source.frames()
        first = [await anext(frames) for _ in range(10)]
        control.request("pause")
        hover = await anext(frames)
        waiting = asyncio.ensure_future(anext(frames))
        await asyncio.sleep(0.05)
        assert not waiting.done()  # no frames while paused
        control.request("resume")
        resumed = await waiting
        await frames.aclose()
        return first, hover, resumed

    first, hover, resumed = asyncio.run(run())
    # One frame at rest where it stopped, without readings.
    assert (hover.position.lat, hover.position.time_boot_ms) == (first[-1].position.lat, first[-1].position.time_boot_ms)
    assert (hover.position.vx, hover.position.vy, hover.sensor) == (0, 0, None)
    # The flight carries on from where it paused: the next sample, 0.2 s of flight later.
    assert resumed.position.time_boot_ms - first[-1].position.time_boot_ms == 200
    assert resumed.sensor is not None


def test_return_home_flies_to_the_start_and_lands_without_readings():
    sim = build_simulation(CONFIG)
    frames = asyncio.run(_fly({100: "return"}))
    after = frames[100:]
    assert after and all(f.sensor is None for f in after)
    last = frames[-1]
    x, y = sim.frame.to_xy(last.position.lat / 1e7, last.position.lon / 1e7)
    assert math.dist((x, y), sim.plan.waypoints_xy[0]) < 0.01
    assert last.position.relative_alt == 0
    assert last.progress == frames[99].progress  # the survey progress stays where it was stopped
    assert last.battery.battery_remaining <= frames[99].battery.battery_remaining


def test_land_comes_down_where_it_is():
    frames = asyncio.run(_fly({100: "land"}))
    stop, last = frames[99].position, frames[-1].position
    assert (last.lat, last.lon) == (stop.lat, stop.lon)
    assert last.relative_alt == 0
    # Straight down at 0.5 m/s, a frame every 0.2 s.
    assert len(frames) - 100 == math.ceil(stop.relative_alt / 1000 / 0.5 / 0.2)


def start(client, headers) -> int:
    mission_id = client.post("/api/missions", json=mission_body(), headers=headers).json()["id"]
    r = client.post(f"/api/missions/{mission_id}/start", json={"speed_factor": 1}, headers=headers)
    assert r.status_code == 202 and r.json()["phase"] == "surveying"
    return mission_id


def control(client, mission_id, action, headers):
    return client.post(f"/api/missions/{mission_id}/control", json={"action": action}, headers=headers)


def test_returned_home_mission_is_stopped_with_its_detections_kept(client):
    headers = auth_headers(client, "supervisor")
    mission_id = start(client, headers)
    r = control(client, mission_id, "pause", headers)
    assert r.status_code == 202 and r.json()["phase"] == "paused"
    assert client.get(f"/api/missions/{mission_id}", headers=headers).json()["phase"] == "paused"
    assert control(client, mission_id, "resume", headers).json()["phase"] == "surveying"
    assert control(client, mission_id, "return", headers).json()["phase"] == "returning"
    mission = wait_until_finished(client, mission_id, headers)
    assert (mission["status"], mission["error"], mission["phase"]) == ("stopped", "Returned home by the supervisor", None)
    assert mission["progress"] < 1
    history = client.get("/api/missions/history", headers=headers).json()
    assert history["stopped"] == 1 and history["missions"][0]["mission"]["id"] == mission_id


def test_control_is_for_the_supervisor_of_a_flying_mission(client):
    supervisor = auth_headers(client, "supervisor")
    planned = client.post("/api/missions", json=mission_body(), headers=supervisor).json()["id"]
    assert control(client, planned, "pause", supervisor).status_code == 409
    assert control(client, 9999, "pause", supervisor).status_code == 404
    flying = start(client, supervisor)
    assert control(client, flying, "takeoff", supervisor).status_code == 422
    assert control(client, flying, "pause", auth_headers(client, "field")).status_code == 403
    r = control(client, flying, "resume", supervisor)
    assert r.status_code == 409 and "not paused" in r.json()["detail"]
    assert control(client, flying, "land", supervisor).status_code == 202
    assert wait_until_finished(client, flying, supervisor)["error"] == "Landed by the supervisor"


def test_live_view_shows_the_phase(client):
    headers = auth_headers(client, "supervisor")
    mission_id = start(client, headers)
    token = headers["Authorization"].removeprefix("Bearer ")
    control(client, mission_id, "pause", headers)
    with client.websocket_connect(f"/ws/missions/{mission_id}?token={token}") as ws:
        assert ws.receive_json()["mission"]["phase"] == "paused"  # after a reload
        control(client, mission_id, "land", headers)
        while (event := ws.receive_json())["type"] != "mission":
            pass
        assert (event["status"], event["phase"]) == ("running", "landing")
    wait_until_finished(client, mission_id, headers)
