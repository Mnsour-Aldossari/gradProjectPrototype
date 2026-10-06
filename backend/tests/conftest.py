from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.seed import DEMO_USERS
from app.simulation import DEMO_AREA


@pytest.fixture
def client(tmp_path):
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}", secret_key="test-secret")
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
