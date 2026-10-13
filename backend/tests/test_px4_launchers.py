"""Starting PX4 SITL at the takeoff point: Gazebo's window in WSL or the headless Docker image, one at a time. The
commands are replaced by stand-ins here; starting the real ones is tested by hand (README, 'Gazebo window')."""

from __future__ import annotations

import asyncio

import pytest
from conftest import auth_headers, mission_body

from app.api.runner import make_source, px4_launchers
from app.config import Settings
from app.simulation import SimulationConfig
from app.uav import px4_docker, px4_gazebo
from app.uav.px4_docker import Px4Docker, Px4RestartFailed
from app.uav.px4_gazebo import Px4Gazebo, mirrored_networking
from app.uav.px4_mavlink_source import Px4MavlinkSource, Px4Unavailable

CONFIG = SimulationConfig(
    area=((24.13968, 47.26170), (24.13968, 47.26230), (24.13932, 47.26230), (24.13932, 47.26170)),
    altitude_m=1.5, speed_mps=2.0, line_spacing_m=2.0, soil_type="dry_sand", seed=1,
)  # fmt: skip
TAKEOFF = (24.13990, 47.26200)


class FakeLauncher:
    def __init__(self, name: str, log: list, running: bool = False, prepare_fails: bool = False) -> None:
        self.name, self.log, self.is_running, self.prepare_fails = name, log, running, prepare_fails

    async def prepare(self) -> None:
        self.log.append((self.name, "prepare"))
        if self.prepare_fails:
            raise Px4RestartFailed("WSL's mirrored networking is off")

    async def running(self) -> bool:
        self.log.append((self.name, "running"))
        return self.is_running

    async def restart_at(self, lat: float, lon: float) -> None:
        self.log.append((self.name, "restart_at", (lat, lon)))

    async def stop(self) -> None:
        self.log.append((self.name, "stop"))


def test_px4_that_is_off_is_started_at_the_takeoff_point_after_the_other_one_stops():
    log: list = []
    source = Px4MavlinkSource(
        CONFIG, takeoff=TAKEOFF, launcher=FakeLauncher("gazebo", log), others=(FakeLauncher("docker", log),)
    )
    assert asyncio.run(source._start_px4_if_off()) is True
    assert log == [("gazebo", "prepare"), ("docker", "stop"), ("gazebo", "running"), ("gazebo", "restart_at", TAKEOFF)]


def test_px4_already_running_is_not_started_again():
    log: list = []
    source = Px4MavlinkSource(CONFIG, takeoff=TAKEOFF, launcher=FakeLauncher("docker", log, running=True))
    assert asyncio.run(source._start_px4_if_off()) is False
    assert ("docker", "restart_at", TAKEOFF) not in log


def test_a_launcher_that_cannot_work_says_why_before_anything_is_stopped():
    log: list = []
    source = Px4MavlinkSource(
        CONFIG,
        takeoff=TAKEOFF,
        launcher=FakeLauncher("gazebo", log, prepare_fails=True),
        others=(FakeLauncher("docker", log),),
    )
    with pytest.raises(Px4Unavailable, match="mirrored networking"):
        asyncio.run(source._start_px4_if_off())
    assert log == [("gazebo", "prepare")]


def test_without_a_launcher_px4_is_left_as_it_is():
    assert asyncio.run(Px4MavlinkSource(CONFIG, takeoff=TAKEOFF)._start_px4_if_off()) is False


def test_gazebo_or_docker_is_chosen_and_the_other_one_stopped():
    both = Settings(secret_key="k", px4_manage_docker=True, px4_manage_gazebo=True, px4_gazebo_distro="Ubuntu-24.04")
    launcher, others = px4_launchers(both, gazebo=True)
    assert isinstance(launcher, Px4Gazebo) and launcher.distro == "Ubuntu-24.04"
    assert [type(o) for o in others] == [Px4Docker]
    launcher, others = px4_launchers(both, gazebo=False)
    assert isinstance(launcher, Px4Docker) and [type(o) for o in others] == [Px4Gazebo]
    assert px4_launchers(Settings(secret_key="k"), gazebo=True) == (None, ())  # tests and servers without them


def test_make_source_passes_gazebo_on():
    from app.models import Mission

    mission = Mission(
        name="m", area=[list(p) for p in CONFIG.area], path=[[24.13932, 47.2617], [24.13932, 47.2623]],
        path_length_m=60, altitude_m=1.5, speed_mps=2.0, line_spacing_m=2.0, soil_type="dry_sand",
        scenario_seed=1, created_by=1, uav_source="px4",
    )  # fmt: skip
    settings = Settings(secret_key="k", px4_manage_docker=True, px4_manage_gazebo=True)
    source = make_source(mission, settings, 1.0, gazebo=True)
    assert isinstance(source.launcher, Px4Gazebo) and source.takeoff is not None  # the default point, outside


def test_gazebo_start_args_carry_only_numbers_and_the_configured_folder():
    args = Px4Gazebo(distro="Ubuntu-22.04", px4_dir="PX4-Autopilot").start_args(24.1395809, 47.2620799)
    assert args == [
        "wsl", "-d", "Ubuntu-22.04", "--exec", "/bin/sh", "-s", "--",
        "24.1395809", "47.2620799", "430.0", "PX4-Autopilot", "gz_x500",
    ]  # fmt: skip
    with pytest.raises(ValueError):
        Px4Gazebo().start_args(float("nan"), 47.0)


@pytest.mark.parametrize(
    ("text", "encoding", "on"),
    [
        ("[wsl2]\nnetworkingMode=mirrored\n", "utf-8", True),
        ("[wsl2]\r\n  networkingmode = Mirrored \r\n", "utf-8", True),
        ("[wsl2]\nnetworkingMode=mirrored\n", "utf-16", True),  # PowerShell's Out-File
        ("[wsl2]\nnetworkingMode=nat\n", "utf-8", False),
        ("[wsl2]\n# networkingMode=mirrored\n", "utf-8", False),
    ],
)
def test_mirrored_networking_is_read_from_wslconfig(tmp_path, text, encoding, on):
    path = tmp_path / ".wslconfig"
    path.write_bytes(text.encode(encoding))
    assert mirrored_networking(path) is on


def test_no_wslconfig_means_no_mirrored_networking(tmp_path):
    assert mirrored_networking(tmp_path / ".wslconfig") is False


def test_gazebo_that_cannot_start_says_what_wsl_printed(tmp_path, monkeypatch):
    class Ended:
        returncode = 4

        def poll(self):
            return 4

    log = tmp_path / "gazebo.log"
    log.write_text("PX4 is not built in PX4-Autopilot: run make px4_sitl gz_x500 there once\n")
    monkeypatch.setattr(px4_gazebo, "LOG", log)
    monkeypatch.setattr(px4_gazebo, "_spawn", lambda args, script: Ended())

    async def no_distro_running(args, script=None):
        return ""

    monkeypatch.setattr(px4_gazebo, "_output", no_distro_running)
    with pytest.raises(Px4RestartFailed, match="PX4 is not built"):
        asyncio.run(Px4Gazebo().restart_at(*TAKEOFF))


def test_gazebo_is_only_stopped_in_its_own_running_distribution(monkeypatch):
    calls = []

    async def wsl(args, script=None):
        calls.append(args)
        return "docker-desktop\nUbuntu\n" if "--running" in args else ""

    monkeypatch.setattr(px4_gazebo, "_output", wsl)
    gazebo = Px4Gazebo(distro="Ubuntu-22.04")
    assert asyncio.run(gazebo.running()) is False
    asyncio.run(gazebo.stop())
    assert all("--running" in a for a in calls)  # Ubuntu-22.04 is not running: nothing else was run in WSL


def test_docker_px4_is_running_when_its_container_runs(monkeypatch):
    async def inspect(args, timeout_s=15.0):
        return "true\n"

    monkeypatch.setattr(px4_docker, "_output", inspect)
    assert asyncio.run(Px4Docker().running()) is True


def test_health_says_whether_gazebo_can_be_started(client):
    health = client.get("/api/health").json()
    assert health["px4_gazebo"] is False and health["px4_manage_off"] is False  # never in tests, and not turned off
    assert health["database"] in ("sqlite", "postgresql")


def test_gazebo_without_wsl_leaves_the_mission_planned(client):
    headers = auth_headers(client, "supervisor")
    mission_id = client.post("/api/missions", json=mission_body(), headers=headers).json()["id"]
    r = client.post(f"/api/missions/{mission_id}/start", json={"uav_source": "px4", "gazebo": True}, headers=headers)
    assert r.status_code == 503 and "WSL" in r.json()["detail"]
    mission = client.get(f"/api/missions/{mission_id}", headers=headers).json()
    assert (mission["status"], mission["uav_source"]) == ("planned", "simulated")
    r = client.post(f"/api/missions/{mission_id}/start", json={"uav_source": "simulated", "gazebo": True}, headers=headers)
    assert r.status_code == 422
