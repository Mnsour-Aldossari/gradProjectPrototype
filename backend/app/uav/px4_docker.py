"""Restarting PX4 SITL (the headless Docker image) with its home at a chosen takeoff point.

PX4 SITL takes its home position only when it starts (PX4_HOME_LAT / PX4_HOME_LON), so flying from another point
means a new container. This runs two fixed commands, `docker stop` and `docker run` of the configured image, with the
coordinates as numbers; nothing else reaches the command line. Used only where the backend runs next to Docker
(a developer machine): without the docker command it is off.
"""

from __future__ import annotations

import asyncio
import math
import shutil
import subprocess
from dataclasses import dataclass

STOP_TIMEOUT_S = 30.0
RUN_TIMEOUT_S = 60.0


class Px4RestartFailed(Exception):
    """Docker could not restart PX4. The message says why."""


@dataclass(frozen=True)
class Px4Docker:
    container: str = "px4-sitl"
    image: str = "jonasvautherin/px4-gazebo-headless:1.17.0"
    home_alt_m: float = 430.0

    @staticmethod
    def available() -> bool:
        return shutil.which("docker") is not None

    def run_args(self, lat: float, lon: float) -> list[str]:
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("takeoff point out of range")
        return [
            "docker", "run", "-dit", "--rm", "--name", self.container,
            "-e", f"PX4_HOME_LAT={lat:.7f}",
            "-e", f"PX4_HOME_LON={lon:.7f}",
            "-e", f"PX4_HOME_ALT={self.home_alt_m:.1f}",
            self.image,
        ]  # fmt: skip

    async def restart_at(self, lat: float, lon: float) -> None:
        args = self.run_args(lat, lon)
        # The container runs with --rm, so once stopped its name is free again.
        await _run(["docker", "stop", self.container], STOP_TIMEOUT_S)
        for _ in range(20):
            if not await _run(["docker", "container", "inspect", self.container], 10):
                break
            await asyncio.sleep(0.5)
        if not await _run(args, RUN_TIMEOUT_S):
            raise Px4RestartFailed(
                f"Docker could not start PX4 at the takeoff point. Check that Docker Desktop is running and the image "
                f"{self.image} is downloaded."
            )


async def _run(args: list[str], timeout_s: float) -> bool:
    """Runs a command without a shell, in a thread (works with any event loop on Windows); True if it exited with 0."""
    try:
        done = await asyncio.to_thread(
            subprocess.run, args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout_s, check=False
        )
    except subprocess.TimeoutExpired:
        raise Px4RestartFailed(f"'{' '.join(args[:2])}' did not finish within {timeout_s:.0f} s") from None
    except OSError as e:
        raise Px4RestartFailed(f"Cannot run docker: {e}") from e
    return done.returncode == 0
