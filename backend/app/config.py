"""Runtime settings, read from environment variables."""

from __future__ import annotations

import os
import secrets
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_URL = f"sqlite:///{(BACKEND_DIR / 'uav.db').as_posix()}"
SECRET_KEY_FILE = BACKEND_DIR / ".secret_key"


def load_or_create_secret_key(path: Path | None = None) -> str:
    """Token signing key used when SECRET_KEY is not set: generated once, then reused so sessions survive restarts."""
    path = path or SECRET_KEY_FILE
    for _ in range(50):
        if path.exists():
            key = path.read_text(encoding="utf-8").strip()
            if key:
                return key
        else:
            try:
                with path.open("x", encoding="utf-8") as f:  # "x": never overwrite a key another process just wrote
                    f.write(secrets.token_urlsafe(48))
                path.chmod(0o600)
            except FileExistsError:
                pass
        time.sleep(0.05)  # another process is still writing the file
    raise RuntimeError(f"Could not read or create the signing key file {path}")


def database_ui_url(value: str) -> str:
    """The link to the database page: only an http(s) address is used (it goes into a link in the browser)."""
    value = value.strip()
    return value if value.lower().startswith(("http://", "https://")) else ""


@dataclass(frozen=True)
class Settings:
    secret_key: str  # no default on purpose: see Settings.from_env
    # e.g. postgresql+psycopg://uav:uav@localhost:5432/uav - no code changes needed to switch.
    database_url: str = DEFAULT_DATABASE_URL
    default_speed_factor: float = 10.0
    # Where PX4 (SITL or a vehicle) sends MAVLink, for missions flown with PX4. MAVSDK listens here.
    px4_url: str = "udpin://0.0.0.0:14540"
    # Start or restart PX4 SITL at a mission's takeoff point: the headless Docker image (where the docker command
    # exists) and Gazebo's window in WSL (on Windows, where wsl exists). PX4_MANAGE_DOCKER=0 turns both off; never on
    # in tests (the defaults here).
    px4_manage_docker: bool = False
    px4_manage_gazebo: bool = False
    px4_manage_off: bool = False  # PX4_MANAGE_DOCKER=0: both off on purpose, whatever is installed
    # A web page for browsing the database (e.g. NocoDB, Adminer), linked in the supervisor's menu. Empty: no link.
    database_ui_url: str = ""
    # Where PX4-Autopilot is built in WSL (make px4_sitl gz_x500): the distribution, and the folder in its home.
    px4_gazebo_distro: str = "Ubuntu-22.04"
    px4_gazebo_dir: str = "PX4-Autopilot"
    token_ttl_s: int = 12 * 3600
    cors_origins: tuple[str, ...] = ("http://localhost:5180", "http://127.0.0.1:5180")

    @classmethod
    def from_env(cls) -> Settings:
        manage = os.environ.get("PX4_MANAGE_DOCKER", "1") != "0"
        return cls(
            database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
            secret_key=os.environ.get("SECRET_KEY") or load_or_create_secret_key(),
            default_speed_factor=float(os.environ.get("SIM_SPEED_FACTOR", "10")),
            px4_url=os.environ.get("PX4_URL", "udpin://0.0.0.0:14540"),
            px4_manage_docker=manage and shutil.which("docker") is not None,
            px4_manage_gazebo=manage and os.name == "nt" and shutil.which("wsl") is not None,
            px4_manage_off=not manage,
            database_ui_url=database_ui_url(os.environ.get("DATABASE_UI_URL", "")),
            px4_gazebo_distro=os.environ.get("PX4_GAZEBO_DISTRO", "Ubuntu-22.04"),
            px4_gazebo_dir=os.environ.get("PX4_GAZEBO_DIR", "PX4-Autopilot"),
        )
