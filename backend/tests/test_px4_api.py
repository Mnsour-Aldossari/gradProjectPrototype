"""Starting missions with PX4 through the API. PX4 itself is replaced by a stand-in that plays the simulator, so
these run without PX4; the real link is tested by hand (README, 'PX4 SITL + Gazebo')."""

from __future__ import annotations

import asyncio

import pytest
from conftest import auth_headers, mission_body, wait_until_finished

from app.simulation import SimulationConfig
from app.uav import SimulatedSource
from app.uav import px4_mavlink_source as px4
from app.uav.px4_mavlink_source import Px4MavlinkSource, Px4Unavailable


class FakePx4(SimulatedSource):
    """Answers like PX4 would and flies the simulator's path."""

    speed_factor = 0.0  # as fast as possible

    def __init__(self, config: SimulationConfig, url: str, takeoff=None, docker=None, landing=None) -> None:
        super().__init__(config, speed_factor=self.speed_factor)
        self.url, self.takeoff, self.docker = url, takeoff, docker

    async def connect(self) -> None:
        pass


class AbsentPx4(FakePx4):
    async def connect(self) -> None:
        raise Px4Unavailable("No PX4 answered on udpin://0.0.0.0:14540 within 10 s. Start PX4 SITL and try again.")


def create(client, headers) -> int:
    r = client.post("/api/missions", json=mission_body(), headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_health_says_whether_the_server_can_talk_to_px4(client):
    assert isinstance(client.get("/api/health").json()["px4_available"], bool)


def test_px4_not_running_leaves_the_mission_planned_with_the_reason(client, monkeypatch):
    monkeypatch.setattr("app.api.runner.Px4MavlinkSource", AbsentPx4)
    headers = auth_headers(client, "supervisor")
    mission_id = create(client, headers)
    r = client.post(f"/api/missions/{mission_id}/start", json={"uav_source": "px4"}, headers=headers)
    assert r.status_code == 503
    assert "Start PX4 SITL" in r.json()["detail"]
    mission = client.get(f"/api/missions/{mission_id}", headers=headers).json()
    assert (mission["status"], mission["uav_source"]) == ("planned", "simulated")


def test_mission_flown_with_px4_is_stored_and_detects_like_the_simulator(client, monkeypatch):
    monkeypatch.setattr("app.api.runner.Px4MavlinkSource", FakePx4)
    headers = auth_headers(client, "supervisor")
    mission_id = create(client, headers)
    r = client.post(f"/api/missions/{mission_id}/start", json={"uav_source": "px4"}, headers=headers)
    assert r.status_code == 202, r.text
    assert r.json()["uav_source"] == "px4"
    mission = wait_until_finished(client, mission_id, headers)
    assert (mission["status"], mission["uav_source"]) == ("completed", "px4")
    assert mission["stats"]["telemetry_points"] > 0
    assert client.get(f"/api/missions/{mission_id}/detections", headers=headers).json()


def test_one_px4_mission_at_a_time(client, monkeypatch):
    class SlowPx4(FakePx4):
        speed_factor = 1.0  # real time: still flying when the second start comes

    monkeypatch.setattr("app.api.runner.Px4MavlinkSource", SlowPx4)
    headers = auth_headers(client, "supervisor")
    first, second = create(client, headers), create(client, headers)
    assert client.post(f"/api/missions/{first}/start", json={"uav_source": "px4"}, headers=headers).status_code == 202
    r = client.post(f"/api/missions/{second}/start", json={"uav_source": "px4"}, headers=headers)
    assert r.status_code == 409 and f"mission {first}" in r.json()["detail"]
    # The simulator is not held up by PX4.
    r = client.post(f"/api/missions/{second}/start", json={"uav_source": "simulated", "speed_factor": 0}, headers=headers)
    assert r.status_code == 202


def test_start_rejects_an_unknown_source(client):
    headers = auth_headers(client, "supervisor")
    mission_id = create(client, headers)
    r = client.post(f"/api/missions/{mission_id}/start", json={"uav_source": "ardupilot"}, headers=headers)
    assert r.status_code == 422


def test_demo_scenario_always_uses_the_simulator(client, monkeypatch):
    monkeypatch.setattr("app.api.runner.Px4MavlinkSource", AbsentPx4)
    r = client.post("/api/missions/demo", json={"speed_factor": 0}, headers=auth_headers(client, "supervisor"))
    assert r.status_code == 202 and r.json()["uav_source"] == "simulated"


@pytest.mark.skipif(not px4.mavsdk_installed(), reason="MAVSDK not installed (requirements-px4.txt)")
def test_real_mavsdk_reports_no_px4_quickly(monkeypatch):
    """The real MAVSDK listening on a port where nothing sends: a clear Px4Unavailable, not a hang."""
    monkeypatch.setattr(px4, "DISCOVERY_TIMEOUT_S", 0.5)
    config = SimulationConfig(
        area=((24.13968, 47.26170), (24.13968, 47.26230), (24.13932, 47.26230), (24.13932, 47.26170)),
        altitude_m=1.5, speed_mps=2.0, line_spacing_m=2.0, soil_type="dry_sand", seed=1,
    )
    source = Px4MavlinkSource(config, url="udpin://0.0.0.0:14597")
    with pytest.raises(Px4Unavailable, match="No PX4 answered"):
        asyncio.run(source.connect())


def test_cancelled_run_lets_the_source_finish(tmp_path, monkeypatch):
    """When the backend shuts down mid-flight, the source's cleanup runs (for PX4: return to launch)."""
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    finished = []

    class EndlessPx4(FakePx4):
        speed_factor = 1.0

        async def frames(self):
            try:
                async for f in super().frames():
                    yield f
            finally:
                finished.append(True)

    monkeypatch.setattr("app.api.runner.Px4MavlinkSource", EndlessPx4)
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'c.db').as_posix()}", secret_key="test-secret")
    with TestClient(create_app(settings)) as c:
        headers = auth_headers(c, "supervisor")
        mission_id = create(c, headers)
        assert c.post(f"/api/missions/{mission_id}/start", json={"uav_source": "px4"}, headers=headers).status_code == 202
        assert not finished
    assert finished == [True]  # leaving the block shut the app down and cancelled the run


def test_live_view_knows_when_the_survey_lines_began(client, monkeypatch):
    """survey_start_s (first sensor reading) comes in live telemetry and in the snapshot after a reload, so the page
    can time the survey without takeoff. The stand-in reads from the start, like the simulator."""
    monkeypatch.setattr("app.api.runner.Px4MavlinkSource", FakePx4)
    headers = auth_headers(client, "supervisor")
    mission_id = create(client, headers)
    token = headers["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(f"/ws/missions/{mission_id}?token={token}") as ws:
        assert ws.receive_json()["last_telemetry"] is None
        client.post(f"/api/missions/{mission_id}/start", json={"uav_source": "px4"}, headers=headers)
        while (event := ws.receive_json())["type"] != "telemetry":
            pass
        assert event["survey_start_s"] == 0.0
    wait_until_finished(client, mission_id, headers)
    with client.websocket_connect(f"/ws/missions/{mission_id}?token={token}") as ws:
        assert ws.receive_json()["last_telemetry"]["survey_start_s"] == 0.0


def test_px4_mission_returned_home_is_stopped(client, monkeypatch):
    class SlowPx4(FakePx4):
        speed_factor = 1.0

    monkeypatch.setattr("app.api.runner.Px4MavlinkSource", SlowPx4)
    headers = auth_headers(client, "supervisor")
    mission_id = create(client, headers)
    assert client.post(f"/api/missions/{mission_id}/start", json={"uav_source": "px4"}, headers=headers).status_code == 202
    r = client.post(f"/api/missions/{mission_id}/control", json={"action": "return"}, headers=headers)
    assert r.status_code == 202 and r.json()["phase"] == "returning"
    mission = wait_until_finished(client, mission_id, headers)
    assert (mission["status"], mission["uav_source"]) == ("stopped", "px4")


def test_takeoff_point_is_set_on_a_planned_mission(client):
    headers = auth_headers(client, "supervisor")
    mission_id = create(client, headers)
    start = client.get(f"/api/missions/{mission_id}", headers=headers).json()["path"][0]
    near = {"lat": start[0] + 0.0002, "lon": start[1]}  # about 22 m north
    r = client.put(f"/api/missions/{mission_id}/takeoff", json=near, headers=headers)
    assert r.status_code == 200 and (r.json()["takeoff_lat"], r.json()["takeoff_lon"]) == (near["lat"], near["lon"])
    far = client.put(f"/api/missions/{mission_id}/takeoff", json={"lat": start[0] + 0.01, "lon": start[1]}, headers=headers)
    assert far.status_code == 422 and "900 m" in far.json()["detail"]
    assert client.put(f"/api/missions/{mission_id}/takeoff", json={"lat": 1.0}, headers=headers).status_code == 422
    assert client.put(f"/api/missions/{mission_id}/takeoff", json=near, headers=auth_headers(client, "field")).status_code == 403
    cleared = client.put(f"/api/missions/{mission_id}/takeoff", json={}, headers=headers).json()
    assert (cleared["takeoff_lat"], cleared["takeoff_lon"]) == (None, None)


class _Home:
    def __init__(self, lat, lon):
        self.latitude_deg, self.longitude_deg = lat, lon


class _Health:
    is_global_position_ok = is_home_position_ok = True


class _FakePx4Link:
    """A PX4 whose home moves once the fake Docker restarts it."""

    def __init__(self, home):
        self.home_at = home

    async def is_connected(self):
        return True

    async def home(self):
        return _Home(*self.home_at)

    async def subscribe_health(self):
        yield _Health()

    async def subscribe_position(self):
        while True:
            yield _Home(*self.home_at)
            await asyncio.sleep(0.01)


def _source(**kw):
    config = SimulationConfig(
        area=((24.13968, 47.26170), (24.13968, 47.26230), (24.13932, 47.26230), (24.13932, 47.26170)),
        altitude_m=1.5, speed_mps=2.0, line_spacing_m=2.0, soil_type="dry_sand", seed=1,
    )
    return Px4MavlinkSource(config, **kw)


def test_px4_is_restarted_at_the_takeoff_point(monkeypatch):
    monkeypatch.setattr(px4, "SETTLE_S", 0.05)
    restarted = []

    class FakeDocker:
        async def restart_at(self, lat, lon):
            restarted.append((lat, lon))
            link.home_at = (lat, lon)

    takeoff = (24.13990, 47.26200)
    source = _source(takeoff=takeoff, docker=FakeDocker())
    link = _FakePx4Link((47.397742, 8.545594))  # PX4's default home, Zurich
    home = asyncio.run(source._home_at_takeoff(link, link, link.home_at))
    assert restarted == [takeoff] and home == takeoff
    # Already there: no restart.
    assert asyncio.run(source._home_at_takeoff(link, link, takeoff)) == takeoff and len(restarted) == 1


def test_without_docker_a_takeoff_point_elsewhere_is_explained():
    source = _source(takeoff=(24.13990, 47.26200))
    link = _FakePx4Link((24.13950, 47.26200))  # 44 m south
    with pytest.raises(Px4Unavailable, match="PX4_HOME_LAT=24.139900"):
        asyncio.run(source._home_at_takeoff(link, link, link.home_at))


def test_after_a_restart_px4_must_hold_still_at_the_takeoff_point(monkeypatch):
    """A new PX4 SITL jumps from its default home to the takeoff point; takeoff waits until its position settles."""
    monkeypatch.setattr(px4, "SETTLE_S", 0.05)
    takeoff = (24.13990, 47.26200)
    seen = []

    class Positions:
        async def subscribe_position(self):
            track = [(47.397742, 8.545594)] * 3 + [(24.13990 + 0.00002 * k, 47.26200) for k in range(5)]
            for lat, lon in track + [takeoff] * 100:  # Zurich, then drifting, then still
                seen.append((lat, lon))
                yield _Home(lat, lon)
                await asyncio.sleep(0.01)

    asyncio.run(Px4MavlinkSource._settled(Positions(), takeoff))
    assert seen[-1] == takeoff and len(seen) > 8  # not before the drift had stopped


def test_takeoff_and_landing_points_shown_with_the_mission(client):
    headers = auth_headers(client, "supervisor")
    mission_id = create(client, headers)
    m = client.get(f"/api/missions/{mission_id}", headers=headers).json()
    start, end = m["path"][0], m["path"][-1]
    assert m["takeoff_point"][1] < start[1] and m["landing_point"] == m["takeoff_point"]  # west of the first lane
    landing = {"lat": end[0] + 0.0001, "lon": end[1]}
    m = client.put(f"/api/missions/{mission_id}/landing", json=landing, headers=headers).json()
    assert m["landing_point"] == [landing["lat"], landing["lon"]] and m["takeoff_point"] != m["landing_point"]
    far = client.put(f"/api/missions/{mission_id}/landing", json={"lat": end[0] + 0.01, "lon": end[1]}, headers=headers)
    assert far.status_code == 422 and "landing point" in far.json()["detail"]
    m = client.put(f"/api/missions/{mission_id}/landing", json={}, headers=headers).json()
    assert m["landing_point"] == m["takeoff_point"]


@pytest.mark.skipif(not px4.mavsdk_installed(), reason="MAVSDK not installed (requirements-px4.txt)")
def test_px4_mission_ends_with_a_landing_at_the_landing_point():
    from mavsdk.plugins.mission import MissionItem

    from app.uav.px4_mavlink_source import _mission_item
    from app.uav.px4_plan import Waypoint

    item = _mission_item(Waypoint(24.1, 47.2, 1.5, 2.0), land=True)
    assert item.vehicle_action == MissionItem.VehicleAction.LAND


def test_px4_a_few_metres_from_the_takeoff_point_is_restarted_there(monkeypatch):
    """PX4 takes off from, and returns home to, the point on the map: 6 m away is too far (it was let off at 25 m)."""
    monkeypatch.setattr(px4, "SETTLE_S", 0.05)
    restarted = []

    class FakeDocker:
        async def restart_at(self, lat, lon):
            restarted.append((lat, lon))
            link.home_at = (lat, lon)

    takeoff = (24.13990, 47.26200)
    source = _source(takeoff=takeoff, docker=FakeDocker())
    link = _FakePx4Link((24.13990, 47.26206))  # 6 m east
    assert asyncio.run(source._home_at_takeoff(link, link, link.home_at)) == takeoff and restarted == [takeoff]


def test_px4_standing_away_from_its_home_is_restarted_at_the_takeoff_point(monkeypatch):
    """After landing at a landing point PX4's home is still the takeoff point, but it would take off where it stands."""
    monkeypatch.setattr(px4, "SETTLE_S", 0.05)
    restarted = []

    class FakeDocker:
        async def restart_at(self, lat, lon):
            restarted.append((lat, lon))
            link.home_at = (lat, lon)

    takeoff = (24.13990, 47.26200)
    source = _source(takeoff=takeoff, docker=FakeDocker())
    link = _FakePx4Link(takeoff)
    assert asyncio.run(source._home_at_takeoff(link, link, takeoff, here=(24.13990, 47.26220))) == takeoff
    assert restarted == [takeoff]


def test_after_a_restart_the_old_home_reported_for_a_moment_is_not_taken(monkeypatch):
    """MAVSDK reports the old PX4's home until the new one is up; a few metres off must not pass as the takeoff point."""
    monkeypatch.setattr(px4, "SETTLE_S", 0.05)
    takeoff = (24.13990, 47.26200)
    old = (24.13990, 47.26206)  # 6 m east

    class FakeDocker:
        async def restart_at(self, lat, lon):
            asyncio.get_running_loop().call_later(0.3, lambda: setattr(link, "home_at", (lat, lon)))

    source = _source(takeoff=takeoff, docker=FakeDocker())
    link = _FakePx4Link(old)
    assert asyncio.run(source._home_at_takeoff(link, link, old)) == takeoff
