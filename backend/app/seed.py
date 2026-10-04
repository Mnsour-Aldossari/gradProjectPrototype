"""Demo accounts for the prototype (test credentials only, not for real use)."""

from __future__ import annotations

import os

from sqlalchemy import Engine
from sqlmodel import Session, select

from .models import Mission, User
from .security import hash_password

DEMO_USERS = (
    {"username": "supervisor", "password": "Supervisor#2026", "full_name": "Mission Supervisor", "role": "supervisor"},
    {"username": "field", "password": "Field#2026", "full_name": "Field Operator", "role": "field_operator"},
)

# On a machine others can reach, set these so the demo passwords above (which are in the repository) do not work.
PASSWORD_ENV = {"supervisor": "SUPERVISOR_PASSWORD", "field": "FIELD_PASSWORD"}


def demo_password(user: dict) -> str:
    return os.environ.get(PASSWORD_ENV[user["username"]]) or user["password"]


def seed_users(engine: Engine) -> None:
    with Session(engine) as session:
        for u in DEMO_USERS:
            if session.exec(select(User).where(User.username == u["username"])).first() is None:
                session.add(
                    User(
                        username=u["username"],
                        full_name=u["full_name"],
                        role=u["role"],
                        password_hash=hash_password(demo_password(u)),
                    )
                )
        session.commit()


def fail_interrupted_missions(engine: Engine) -> None:
    """Missions left 'running' by a previous server process can never finish."""
    with Session(engine) as session:
        for mission in session.exec(select(Mission).where(Mission.status == "running")):
            mission.status = "failed"
            mission.error = "Interrupted by a server restart"
            session.add(mission)
        session.commit()
