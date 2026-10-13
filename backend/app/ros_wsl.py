"""Starting and stopping the project's ROS 2 nodes (ros2_ws) in WSL from the dashboard, on Windows.

The supervisor's button runs the same launch file as the README's commands: landmine.launch.py (the mission bridge,
the detector node and mission control), or px4.launch.py landmine:=true where PX4's messages are built (the agent and
px4_link too). The nodes reach the backend on localhost through WSL's mirrored networking, with a token of the
supervisor who pressed the button instead of a password, so nobody types one. As with Gazebo's window, a fixed script
is fed to bash in WSL: the token is in what bash reads, never on a command line; the checkout's folder and the
backend's address are its arguments. ros2_ws/build.sh must have been run once in that distribution.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from .uav.px4_gazebo import _FLAGS, _env, _output

CHECKOUT = Path(__file__).resolve().parents[2]  # the project's folder: backend/app/ros_wsl.py
TOKEN = re.compile(r"^[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+$")  # app.security's tokens
URL = re.compile(r"^https?://[A-Za-z0-9.\-]+:\d{1,5}$")
STARTED_S = 20.0  # ROS 2's launch takes a few seconds; a start that cannot work ends within this

# $1 the checkout as WSL sees it, $2 the backend's address. UAV_TOKEN comes before it, in the same input.
START_SCRIPT = r"""
REPO=$1 URL=$2
[ -f "$REPO/ros2_ws/env.sh" ] || { echo "The project was not found in WSL at $REPO"; exit 3; }
WS="${UAV_ROS_WS:-$HOME/uav_landmine_ws}"
[ -f "$WS/install/setup.bash" ] || { echo "ROS 2 is not built in WSL: run bash $REPO/ros2_ws/build.sh once"; exit 4; }
source "$REPO/ros2_ws/env.sh" || exit 5
command -v ros2 >/dev/null || { echo "ROS 2 (ros2) was not found in WSL"; exit 5; }
export UAV_TOKEN UAV_CONTROL_TOKEN="$UAV_TOKEN"
if [ -d "$WS/install/px4_msgs" ] && [ -d "$WS/install/microxrcedds_agent" ]; then
  set -- px4.launch.py landmine:=true
else
  set -- landmine.launch.py
fi
if pgrep -f 'ros2 launch uav_landmine_ros' >/dev/null; then
  echo "ROS 2 already runs in a WSL terminal: stop it there (Ctrl+C) first, or use that one"; exit 6
fi
echo $$ > /tmp/uav-ros.owner
exec ros2 launch uav_landmine_ros "$@" backend_url:="$URL" >/tmp/uav-ros.log 2>&1 </dev/null
"""

# The launch that the button started (its pid, since exec kept it), still there.
RUNNING_SCRIPT = r"""
P=$(cat /tmp/uav-ros.owner 2>/dev/null)
[ -n "$P" ] && tr '\0' ' ' < "/proc/$P/cmdline" 2>/dev/null | grep -q 'ros2 launch uav_landmine_ros'
"""

# Ctrl+C for the launch, which stops its nodes; then by force if it has not ended.
STOP_SCRIPT = r"""
P=$(cat /tmp/uav-ros.owner 2>/dev/null)
[ -n "$P" ] && tr '\0' ' ' < "/proc/$P/cmdline" 2>/dev/null | grep -q 'ros2 launch uav_landmine_ros' || exit 0
kill -INT "$P"
i=0
while kill -0 "$P" 2>/dev/null; do
  i=$((i + 1))
  if [ $i -eq 30 ]; then kill -TERM "$P"; fi
  if [ $i -gt 40 ]; then kill -KILL "$P"; fi
  if [ $i -gt 50 ]; then exit 1; fi
  sleep 0.5
done
rm -f /tmp/uav-ros.owner
"""

LOG_SCRIPT = "tail -c 4000 /tmp/uav-ros.log 2>/dev/null\n"


class RosStartFailed(RuntimeError):
    pass


def wsl_path(path: Path | str) -> str:
    """C:\\Users\\x -> /mnt/c/Users/x (WSL's default mount of a Windows drive); a POSIX path stays as it is."""
    p = PureWindowsPath(str(path))
    if not p.drive or not p.drive.endswith(":"):
        return str(path).replace("\\", "/")
    return "/mnt/" + p.drive[0].lower() + "/" + "/".join(p.parts[1:])


@dataclass(frozen=True)
class RosInWsl:
    distro: str = "Ubuntu-24.04"
    checkout: Path = CHECKOUT

    @staticmethod
    def available() -> bool:
        return os.name == "nt" and shutil.which("wsl") is not None

    def _wsl(self, *args: str) -> list[str]:
        return ["wsl", "-d", self.distro, "--exec", "/bin/bash", "-s", *args]

    def start_args(self, backend_url: str) -> list[str]:
        if not URL.match(backend_url):
            raise ValueError("backend address not understood")
        return self._wsl("--", wsl_path(self.checkout), backend_url)

    async def running(self) -> bool:
        # Asking a distribution that is not running would start it: a look at the dashboard must not.
        out = await _output(["wsl", "-l", "--running", "-q"])
        if out is None or self.distro not in (line.strip() for line in out.splitlines()):
            return False
        return await _output(self._wsl(), RUNNING_SCRIPT) is not None

    async def stop(self) -> None:
        if await _output(self._wsl(), STOP_SCRIPT) is None:
            raise RosStartFailed("ROS 2 did not stop in WSL")

    async def log(self) -> str:
        out = await _output(self._wsl(), LOG_SCRIPT)
        return (out or "").strip()

    async def start(self, backend_url: str, token: str) -> None:
        if not TOKEN.match(token):
            raise ValueError("token not understood")
        args = self.start_args(backend_url)
        if await self.running():
            return
        script = f"UAV_TOKEN='{token}'\n{START_SCRIPT}"
        try:
            proc = await asyncio.to_thread(_spawn, args, script)
        except OSError as e:
            raise RosStartFailed(f"Cannot run wsl: {e}") from e
        # A start that cannot work ends at once with the reason; a good one is running its nodes by then.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + STARTED_S
        while loop.time() < deadline:
            if proc.poll() is not None:
                said = proc.stdout.read().decode("utf-8", errors="replace").replace("\x00", "") if proc.stdout else ""
                said = " ".join(said.split())[:300] or (await self.log())[-300:] or f"exit code {proc.returncode}"
                raise RosStartFailed(f"ROS 2 did not start in WSL ({self.distro}): {said}")
            if await self.running():
                return
            await asyncio.sleep(0.5)
        raise RosStartFailed(f"ROS 2 did not start in WSL ({self.distro}) within {STARTED_S:.0f} s")


def _spawn(args: list[str], script: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=_env(), creationflags=_FLAGS
    )
    assert proc.stdin is not None
    proc.stdin.write(script.encode())
    proc.stdin.close()
    return proc
