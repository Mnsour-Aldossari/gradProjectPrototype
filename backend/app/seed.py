"""Demo accounts for the prototype (test credentials only, not for real use)."""

from __future__ import annotations

from sqlalchemy import Engine
from sqlmodel import Session, select

from .api.collection import apply, assess_stored
from .models import Mission, User
from .security import hash_password

DEMO_USERS = (
    {"username": "supervisor", "password": "Supervisor#2026", "full_name": "Mission Supervisor", "role": "supervisor"},
    {"username": "field", "password": "Field#2026", "full_name": "Field Operator", "role": "field_operator"},
)


def seed_users(engine: Engine) -> None:
    with Session(engine) as session:
        for u in DEMO_USERS:
            if session.exec(select(User).where(User.username == u["username"])).first() is None:
                session.add(
                    User(
                        username=u["username"],
                        full_name=u["full_name"],
                        role=u["role"],
                        password_hash=hash_password(u["password"]),
                    )
                )
        session.commit()


def fail_interrupted_missions(engine: Engine) -> None:
    """Missions left 'running' by a previous server process can never finish. Their sensor collection is assessed
    from the readings stored before the stop."""
    with Session(engine) as session:
        for mission in session.exec(select(Mission).where(Mission.status == "running")).all():
            mission.status = "failed"
            mission.error = "Interrupted by a server restart"
            apply(mission, assess_stored(session, mission, "The server stopped before the last lane"))
            session.add(mission)
        session.commit()
