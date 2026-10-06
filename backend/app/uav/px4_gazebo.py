"""Starting PX4 SITL with Gazebo's window, in WSL on Windows, with its home at a chosen takeoff point.

The headless Docker image has no window. To watch a survey in Gazebo, PX4-Autopilot is built once in WSL (Ubuntu,
`make px4_sitl gz_x500`) and WSL uses mirrored networking, so PX4's MAVLink reaches the backend on localhost and
Gazebo's window opens on the Windows desktop (WSLg). The backend then starts PX4 and Gazebo there by itself: a fixed
script is fed to sh in WSL, with the coordinates as numbers and the folder and model as arguments, so nothing else
reaches a command line. Closing Gazebo's window stops PX4 too. Only where wsl.exe exists (a developer's Windows PC).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .px4_docker import Px4RestartFailed

COMMAND_TIMEOUT_S = 30.0
EARLY_EXIT_S = 5.0  # a start that cannot work (no distribution, PX4 not built) ends within this
LOG = Path(tempfile.gettempdir()) / "uav-px4-gazebo.log"  # what WSL printed when a start failed

logger = logging.getLogger(__name__)

# PX4 SITL without its shell (-d) and with only Gazebo's server (HEADLESS), then Gazebo's window in the foreground once
# the world runs. When the window closes, PX4 and Gazebo stop, unless a newer start owns them by then.
START_SCRIPT = r"""
LAT=$1 LON=$2 ALT=$3 DIR=$4 MODEL=$5
cd "$HOME" && cd "$DIR" 2>/dev/null || { echo "PX4-Autopilot was not found in WSL: $DIR"; exit 3; }
[ -x build/px4_sitl_default/bin/px4 ] || { echo "PX4 is not built in $DIR: run make px4_sitl $MODEL there once"; exit 4; }
command -v gz >/dev/null || { echo "Gazebo (gz) is not installed in WSL"; exit 5; }
echo $$ > /tmp/uav-gazebo.owner
export GZ_IP=127.0.0.1
cd build/px4_sitl_default/rootfs
HEADLESS=1 PX4_SIM_MODEL=$MODEL PX4_HOME_LAT=$LAT PX4_HOME_LON=$LON PX4_HOME_ALT=$ALT \
  ../bin/px4 -d </dev/null >/tmp/uav-px4.log 2>&1 &
PX4=$!
i=0
until gz topic -l 2>/dev/null | grep -q '^/world/.*/clock'; do
  i=$((i + 1))
  if [ $i -gt 120 ] || ! kill -0 $PX4 2>/dev/null; then break; fi
  sleep 1
done
kill -0 $PX4 2>/dev/null || exit 6
gz sim -g </dev/null >/tmp/uav-gazebo-gui.log 2>&1
if [ "$(cat /tmp/uav-gazebo.owner 2>/dev/null)" = "$$" ]; then
  pkill -x px4; pkill -f 'gz sim'
fi
"""

# PX4 and Gazebo's window are both up.
RUNNING_SCRIPT = "pgrep -x px4 >/dev/null && pgrep -f 'gz sim (-g|gui)' >/dev/null\n"

# The start script that owns PX4 and Gazebo goes first, so that it cannot stop the next ones when its window closes.
STOP_SCRIPT = r"""
OWNER=$(cat /tmp/uav-gazebo.owner 2>/dev/null)
if [ -n "$OWNER" ] && tr '\0' ' ' < "/proc/$OWNER/cmdline" 2>/dev/null | grep -q '^/bin/sh -s -- '; then
  kill "$OWNER"
fi
pkill -x px4; pkill -f 'gz sim'
i=0
while pgrep -x px4 >/dev/null || pgrep -f 'gz sim' >/dev/null; do
  i=$((i + 1))
  if [ $i -eq 10 ]; then pkill -9 -x px4; pkill -9 -f 'gz sim'; fi
  if [ $i -gt 20 ]; then exit 1; fi
  sleep 0.5
done
"""

# Windows: no console window for wsl.exe, and outside the backend's console group, so stopping the backend with
# Ctrl+C leaves Gazebo open.
_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def mirrored_networking(path: Path | None = None) -> bool:
    """Whether .wslconfig turns on WSL's mirrored networking, which lets PX4 in WSL reach the backend on localhost."""
    path = path or Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".wslconfig"
    try:
        text = path.read_bytes().decode("utf-8-sig", errors="replace").replace("\x00", "")
    except OSError:
        return False
    return re.search(r"^\s*networkingMode\s*=\s*mirrored\s*$", text, re.IGNORECASE | re.MULTILINE) is not None


@dataclass(frozen=True)
class Px4Gazebo:
    distro: str = "Ubuntu-22.04"
    px4_dir: str = "PX4-Autopilot"  # in the WSL user's home, or an absolute path
    model: str = "gz_x500"
    home_alt_m: float = 430.0

    @staticmethod
    def available() -> bool:
        return os.name == "nt" and shutil.which("wsl") is not None

    def _wsl(self, *args: str) -> list[str]:
        return ["wsl", "-d", self.distro, "--exec", "/bin/sh", "-s", *args]

    def start_args(self, lat: float, lon: float) -> list[str]:
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("takeoff point out of range")
        return self._wsl("--", f"{lat:.7f}", f"{lon:.7f}", f"{self.home_alt_m:.1f}", self.px4_dir, self.model)

    async def prepare(self) -> None:
        if not mirrored_networking():
            raise Px4RestartFailed(
                "Gazebo in WSL needs WSL's mirrored networking so that PX4 reaches the backend: add "
                "networkingMode=mirrored under [wsl2] in %USERPROFILE%\\.wslconfig, run wsl --shutdown, then try again."
            )

    async def running(self) -> bool:
        return await self._distro_running() and await self._sh(RUNNING_SCRIPT)

    async def stop(self) -> None:
        if await self._distro_running() and not await self._sh(STOP_SCRIPT):
            logger.warning("PX4 or Gazebo in WSL did not stop")

    async def restart_at(self, lat: float, lon: float) -> None:
        args = self.start_args(lat, lon)
        await self.stop()
        try:
            proc = await asyncio.to_thread(_spawn, args, START_SCRIPT)
        except OSError as e:
            raise Px4RestartFailed(f"Cannot run wsl: {e}") from e
        # PX4 and Gazebo take tens of seconds; a start that cannot work ends at once, with WSL's reason.
        deadline = time.monotonic() + EARLY_EXIT_S
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                said = _read_log() or f"exit code {proc.returncode}"
                raise Px4RestartFailed(f"Gazebo did not start in WSL ({self.distro}): {said}")
            await asyncio.sleep(0.25)

    async def _distro_running(self) -> bool:
        out = await _output(["wsl", "-l", "--running", "-q"])
        return out is not None and self.distro in (line.strip() for line in out.splitlines())

    async def _sh(self, script: str) -> bool:
        return await _output(self._wsl(), script) is not None


def _env() -> dict[str, str]:
    return {**os.environ, "WSL_UTF8": "1"}  # wsl.exe's own messages in UTF-8, not UTF-16


def _spawn(args: list[str], script: str) -> subprocess.Popen:
    with open(LOG, "wb") as log:  # the child keeps its own handle
        proc = subprocess.Popen(
            args, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, env=_env(), creationflags=_FLAGS
        )
    assert proc.stdin is not None
    proc.stdin.write(script.encode())
    proc.stdin.close()
    return proc


def _read_log() -> str:
    with contextlib.suppress(OSError):
        return " ".join(LOG.read_bytes().decode("utf-8", errors="replace").replace("\x00", "").split())[:300]
    return ""


async def _output(args: list[str], script: str | None = None) -> str | None:
    """Runs wsl without a shell on the Windows side, in a thread; its output if it exited with 0, else None."""
    try:
        done = await asyncio.to_thread(
            subprocess.run,
            args,
            input=None if script is None else script.encode(),
            capture_output=True,
            timeout=COMMAND_TIMEOUT_S,
            env=_env(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("wsl did not answer: %s", e)
        return None
    if done.returncode != 0:
        return None
    return done.stdout.decode("utf-8", errors="replace").replace("\x00", "")
