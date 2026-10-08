from __future__ import annotations

import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import Settings
from app.main import create_app
from app.seed import DEMO_USERS
from app.simulation import DEMO_AREA


@pytest.fixture
def database_url(tmp_path):
    """A fresh empty database for one test: a SQLite file, or with TEST_DATABASE_URL set (a PostgreSQL server, e.g.
    postgresql+psycopg://user:pass@localhost:5433/db) a schema of its own there, dropped afterwards."""
    server = os.environ.get("TEST_DATABASE_URL")
    if not server:
        yield f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
        return
    schema = f"t_{uuid.uuid4().hex[:12]}"
    admin = create_engine(server)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        yield f"{server}{'&' if '?' in server else '?'}options=-csearch_path%3D{schema}"
    finally:
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def client(database_url):
    settings = Settings(database_url=database_url, secret_key="test-secret")
    with TestClient(create_app(settings)) as c:
        yield c


def auth_headers(client: TestClient, username: str) -> dict[str, str]:
    password = next(u["password"] for u in DEMO_USERS if u["username"] == username)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def mission_body(**overrides) -> dict:
    body = {
        "name": "Test survey",
        "area": [list(p) for p in DEMO_AREA],
        "altitude_m": 1.5,
        "speed_mps": 3.0,
        "line_spacing_m": 2.5,
        "soil_type": "dry_sand",
        "scenario_seed": 11,
    }
    body.update(overrides)
    return body


def wait_until_finished(client: TestClient, mission_id: int, headers: dict, timeout_s: float = 60) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        mission = client.get(f"/api/missions/{mission_id}", headers=headers).json()
        if mission["status"] in ("completed", "stopped", "failed"):
            return mission
        time.sleep(0.05)
    raise AssertionError(f"mission {mission_id} did not finish within {timeout_s}s")
