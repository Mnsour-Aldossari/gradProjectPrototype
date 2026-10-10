"""Login hardening: failed-login throttling, input length limits, and configurable demo accounts."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.login_throttle import LoginThrottle
from app.main import create_app
from app.seed import DEMO_USERS, seeded_users

SUPERVISOR = next(u for u in DEMO_USERS if u["username"] == "supervisor")


def _login(client: TestClient, username: str, password: str):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_repeated_failures_are_blocked_with_retry_after(client):
    for _ in range(5):
        assert _login(client, "supervisor", "wrong").status_code == 401
    blocked = _login(client, "supervisor", "wrong")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1
    # even the right password waits: otherwise the block would not slow a guesser down
    assert _login(client, "supervisor", SUPERVISOR["password"]).status_code == 429


def test_a_block_is_per_username(client):
    for _ in range(5):
        _login(client, "supervisor", "wrong")
    assert _login(client, "supervisor", "wrong").status_code == 429
    assert _login(client, "field", "wrong").status_code == 401  # a different account is not locked out


def test_success_resets_the_failure_count(client):
    for _ in range(3):
        assert _login(client, "supervisor", "wrong").status_code == 401
    assert _login(client, "supervisor", SUPERVISOR["password"]).status_code == 200
    for _ in range(3):
        assert _login(client, "supervisor", "wrong").status_code == 401  # would be blocked had the count carried on


def test_oversized_credentials_are_rejected_before_hashing(client):
    assert _login(client, "supervisor", "x" * 257).status_code == 422
    assert _login(client, "u" * 65, "x").status_code == 422


def test_throttle_window_expires():
    now = [0.0]
    throttle = LoginThrottle(max_failures=2, window_s=10, clock=lambda: now[0])
    throttle.record_failure("1.2.3.4", "Alice")
    throttle.record_failure("1.2.3.4", "alice")  # the username match ignores case and spaces
    assert throttle.retry_after("1.2.3.4", " ALICE ") > 0
    assert throttle.retry_after("5.6.7.8", "alice") == 0  # another client address
    now[0] = 10.0
    assert throttle.retry_after("1.2.3.4", "alice") == 0


def test_seed_password_comes_from_the_environment(database_url, monkeypatch):
    monkeypatch.setenv("SEED_SUPERVISOR_PASSWORD", "from-env-not-source")
    with TestClient(create_app(Settings(database_url=database_url, secret_key="test-secret"))) as c:
        assert _login(c, "supervisor", "from-env-not-source").status_code == 200
        assert _login(c, "supervisor", SUPERVISOR["password"]).status_code == 401


def test_demo_accounts_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("SEED_DEMO_USERS", "0")
    assert seeded_users() == ()
