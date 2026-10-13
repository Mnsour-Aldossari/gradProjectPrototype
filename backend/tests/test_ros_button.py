"""The dashboard's ROS 2 button: supervisors only, the nodes get a token and never a password, and WSL is replaced by a
stand-in here (starting the real nodes is tested by hand: README, 'ROS 2')."""

from __future__ import annotations

import asyncio

import pytest
from conftest import auth_headers

from app import ros_wsl
from app.ros_wsl import RosInWsl, RosStartFailed, wsl_path
from app.security import decode_token


class FakeRos:
    def __init__(self, fails: str = "") -> None:
        self.is_running, self.fails, self.started = False, fails, []

    async def running(self) -> bool:
        return self.is_running

    async def start(self, backend_url: str, token: str) -> None:
        if self.fails:
            raise RosStartFailed(self.fails)
        self.started.append((backend_url, token))
        self.is_running = True

    async def stop(self) -> None:
        self.is_running = False


def test_only_a_supervisor_starts_ros_and_the_nodes_get_a_token_of_theirs(client):
    ros = client.app.state.ros = FakeRos()
    field, supervisor = auth_headers(client, "field"), auth_headers(client, "supervisor")
    assert client.get("/api/ros", headers=field).status_code == 403
    assert client.post("/api/ros/start", headers=field).status_code == 403
    assert client.get("/api/ros", headers=supervisor).json()["running"] is False
    r = client.post("/api/ros/start", headers=supervisor)
    assert r.status_code == 200 and r.json()["running"] is True
    [(url, token)] = ros.started
    assert url.startswith("http://127.0.0.1:")
    assert decode_token(token, "test-secret")["role"] == "supervisor"
    r = client.post("/api/ros/stop", headers=supervisor)
    assert r.status_code == 200 and r.json()["running"] is False


def test_a_start_that_fails_says_why_and_without_wsl_there_is_no_button(client):
    supervisor = auth_headers(client, "supervisor")
    client.app.state.ros = FakeRos(fails="ROS 2 is not built in WSL: run bash ros2_ws/build.sh once")
    r = client.post("/api/ros/start", headers=supervisor)
    assert r.status_code == 502 and "build.sh" in r.json()["detail"]
    client.app.state.ros = None  # the default in tests, and on Linux
    assert client.get("/api/ros", headers=supervisor).json()["available"] is False
    assert client.post("/api/ros/start", headers=supervisor).status_code == 409


def test_the_token_goes_in_what_bash_reads_never_on_the_command_line(monkeypatch):
    spawned = []

    def spawn(args, script):
        spawned.append((args, script))
        raise OSError("no wsl here")

    async def not_running(self):
        return False

    monkeypatch.setattr(ros_wsl, "_spawn", spawn)
    monkeypatch.setattr(RosInWsl, "running", not_running)
    ros = RosInWsl("Ubuntu-24.04", checkout=r"C:\Users\Admin\My project")
    with pytest.raises(RosStartFailed, match="no wsl here"):
        asyncio.run(ros.start("http://127.0.0.1:8000", "abc_-1.def-_2"))
    [(args, script)] = spawned
    assert args == ["wsl", "-d", "Ubuntu-24.04", "--exec", "/bin/bash", "-s", "--",
                    "/mnt/c/Users/Admin/My project", "http://127.0.0.1:8000"]  # fmt: skip
    assert script.startswith("UAV_TOKEN='abc_-1.def-_2'\n")
    with pytest.raises(ValueError):
        asyncio.run(ros.start("http://127.0.0.1:8000", "x'; rm -rf ~; '"))
    with pytest.raises(ValueError):
        ros.start_args("http://127.0.0.1:8000/$(id)")


def test_windows_folders_as_wsl_sees_them():
    assert wsl_path(r"D:\uav\repo") == "/mnt/d/uav/repo"
    assert wsl_path("/home/me/repo") == "/home/me/repo"
