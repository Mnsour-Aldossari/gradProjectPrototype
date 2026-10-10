"""Login hardening: failed-login throttling, input length limits, and configurable demo accounts."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import Settings
from app.login_throttle import LoginThrottle
from app.main import create_app
from app.models import User
from app.security import create_token, hash_password, verify_password
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


def test_a_password_change_ends_the_sessions_opened_with_the_old_password(client):
    token = _login(client, "supervisor", SUPERVISOR["password"]).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    with Session(client.app.state.engine) as session:
        user = session.exec(select(User).where(User.username == "supervisor")).one()
        user.password_hash = hash_password("a-new-password")
        session.add(user)
        session.commit()
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert _login(client, "supervisor", "a-new-password").status_code == 200


def test_a_token_without_the_password_fingerprint_is_refused(client):
    with Session(client.app.state.engine) as session:
        user_id = session.exec(select(User).where(User.username == "supervisor")).one().id
    old_style = create_token(user_id, "supervisor", "test-secret", 3600)  # signed correctly, but no fingerprint
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_style}"}).status_code == 401


def test_a_malformed_stored_hash_is_a_failed_login_not_a_500():
    assert verify_password("x", "not-a-hash") is False
    assert verify_password("x", "pbkdf2_sha256$abc$zz$00") is False  # iterations and salt are not valid


def test_unknown_username_is_a_plain_401(client):
    assert _login(client, "nobody", "whatever").status_code == 401


def test_demo_accounts_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("SEED_DEMO_USERS", "0")
    assert seeded_users() == ()
