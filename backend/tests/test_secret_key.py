"""The token signing key is never a value that is written in the source code."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config
from app.config import Settings, load_or_create_secret_key
from app.main import create_app
from app.security import create_token

OLD_DEFAULT_SECRET = "dev-only-secret-change-me"  # was the built-in key; anyone who read the code knew it


@pytest.fixture
def env_settings(tmp_path, monkeypatch):
    """Settings.from_env() with no SECRET_KEY set, a temporary key file and a temporary database."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setattr(config, "SECRET_KEY_FILE", tmp_path / ".secret_key")
    return tmp_path


def test_token_signed_with_the_old_default_secret_is_rejected(env_settings):
    with TestClient(create_app(Settings.from_env())) as client:
        forged = create_token(1, "supervisor", OLD_DEFAULT_SECRET, 3600)
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert r.status_code == 401

        # control: the same request with a token from a real login works
        login = client.post("/api/auth/login", json={"username": "supervisor", "password": "Supervisor#2026"})
        assert login.status_code == 200
        ok = client.get("/api/auth/me", headers={"Authorization": f"Bearer {login.json()['token']}"})
        assert ok.status_code == 200


def test_generated_key_is_strong_and_reused_on_the_next_start(env_settings):
    first = Settings.from_env().secret_key
    second = Settings.from_env().secret_key
    assert first == second
    assert first != OLD_DEFAULT_SECRET
    assert len(first) >= 43  # token_urlsafe(48) is 64 characters; 43 is 256 bits
    assert (env_settings / ".secret_key").read_text(encoding="utf-8").strip() == first


def test_secret_key_from_the_environment_wins_and_creates_no_file(env_settings, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "key-from-the-environment")
    assert Settings.from_env().secret_key == "key-from-the-environment"
    assert not (env_settings / ".secret_key").exists()


def test_existing_key_file_is_never_overwritten(tmp_path):
    path = tmp_path / ".secret_key"
    path.write_text("existing-key\n", encoding="utf-8")
    assert load_or_create_secret_key(path) == "existing-key"
    assert path.read_text(encoding="utf-8") == "existing-key\n"
