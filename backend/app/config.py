"""Runtime settings, read from environment variables."""

from __future__ import annotations

import os
import secrets
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


@dataclass(frozen=True)
class Settings:
    secret_key: str  # no default on purpose: see Settings.from_env
    # e.g. postgresql+psycopg://uav:uav@localhost:5432/uav - no code changes needed to switch.
    database_url: str = DEFAULT_DATABASE_URL
    default_speed_factor: float = 10.0
    uav_source: str = "simulated"  # "simulated" | "px4" (future phase)
    token_ttl_s: int = 12 * 3600
    cors_origins: tuple[str, ...] = ("http://localhost:5180", "http://127.0.0.1:5180")

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
            secret_key=os.environ.get("SECRET_KEY") or load_or_create_secret_key(),
            default_speed_factor=float(os.environ.get("SIM_SPEED_FACTOR", "10")),
            uav_source=os.environ.get("UAV_SOURCE", "simulated"),
        )
