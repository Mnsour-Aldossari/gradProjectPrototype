"""Demo accounts for the prototype (test credentials only, not for real use)."""

from __future__ import annotations

import os

from sqlalchemy import Engine
from sqlmodel import Session, select

from .api.collection import apply, assess_stored
from .models import Mission, User
from .security import hash_password, verify_password

# Easy to type for a local demo: each password is the username.
DEMO_USERS = (
    {"username": "admin", "password": "admin", "full_name": "Mission Supervisor", "role": "supervisor"},
    {"username": "field", "password": "field", "full_name": "Field Operator", "role": "field_operator"},
)


def seeded_users() -> tuple[dict, ...]:
    """The accounts to create at startup. SEED_DEMO_USERS=0 creates none (use this on anything but a local trial);
    SEED_SUPERVISOR_PASSWORD and SEED_FIELD_PASSWORD replace the demo passwords that are written in the source."""
    if os.environ.get("SEED_DEMO_USERS", "1") == "0":
        return ()
    overrides = {
        "admin": os.environ.get("SEED_SUPERVISOR_PASSWORD"),
        "field": os.environ.get("SEED_FIELD_PASSWORD"),
    }
    return tuple({**u, "password": overrides.get(u["username"]) or u["password"]} for u in DEMO_USERS)


# The supervisor's demo account had another name before; an older database keeps its missions under it.
RENAMED = {"supervisor": "admin"}


def seed_users(engine: Engine) -> None:
    """Creates the demo accounts. One that already exists gets the seeded password back if it has another one (the
    demo passwords were changed to easy ones), so the accounts always open with what seed.py says."""
    users = seeded_users()
    if not users:
        return
    with Session(engine) as session:
        for old, new in RENAMED.items():
            if session.exec(select(User).where(User.username == new)).first() is None:
                user = session.exec(select(User).where(User.username == old)).first()
                if user is not None:
                    user.username = new
                    session.add(user)
        for u in users:
            user = session.exec(select(User).where(User.username == u["username"])).first()
            if user is None:
                session.add(
                    User(
                        username=u["username"],
                        full_name=u["full_name"],
                        role=u["role"],
                        password_hash=hash_password(u["password"]),
                    )
                )
            elif not verify_password(u["password"], user.password_hash):
                user.password_hash = hash_password(u["password"])
                session.add(user)
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
