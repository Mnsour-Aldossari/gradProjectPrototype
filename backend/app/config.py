"""Runtime settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_URL = f"sqlite:///{(BACKEND_DIR / 'uav.db').as_posix()}"
DEV_SECRET_KEY = "dev-only-secret-change-me"


@dataclass(frozen=True)
class Settings:
    # e.g. postgresql+psycopg://uav:uav@localhost:5432/uav - no code changes needed to switch.
    database_url: str = DEFAULT_DATABASE_URL
    secret_key: str = DEV_SECRET_KEY
    default_speed_factor: float = 10.0
    uav_source: str = "simulated"  # "simulated" | "px4" (future phase)
    token_ttl_s: int = 12 * 3600
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
            secret_key=os.environ.get("SECRET_KEY", DEV_SECRET_KEY),
            default_speed_factor=float(os.environ.get("SIM_SPEED_FACTOR", "10")),
            uav_source=os.environ.get("UAV_SOURCE", "simulated"),
        )
