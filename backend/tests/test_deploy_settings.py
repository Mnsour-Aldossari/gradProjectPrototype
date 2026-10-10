"""Deployment settings: where the signing key is kept, which pages may call the API, and what CORS allows."""

from __future__ import annotations

from app.config import Settings, cors_origins

LOCAL = ("http://localhost:5180", "http://127.0.0.1:5180")


def test_cors_origins_come_from_a_comma_separated_list():
    assert cors_origins("https://uav.example.org, http://localhost:5180/ ,", LOCAL) == (
        "https://uav.example.org",
        "http://localhost:5180",
    )


def test_cors_origins_default_to_the_local_ones_when_unset_or_blank():
    assert cors_origins("", LOCAL) == LOCAL
    assert cors_origins(" , ", LOCAL) == LOCAL


def test_secret_key_file_from_the_environment_is_used_for_the_generated_key(tmp_path, monkeypatch):
    key_file = tmp_path / "volume" / ".secret_key"
    key_file.parent.mkdir()
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("SECRET_KEY_FILE", str(key_file))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    first = Settings.from_env().secret_key
    assert key_file.read_text(encoding="utf-8").strip() == first
    assert Settings.from_env().secret_key == first  # reused on the next start, as the default file is


def test_cors_origins_setting_is_read_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("CORS_ORIGINS", "https://uav.example.org")
    assert Settings.from_env().cors_origins == ("https://uav.example.org",)


def _preflight(client, origin: str, method: str, headers: str = "authorization"):
    return client.options(
        "/api/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": headers,
        },
    )


def test_a_local_page_may_call_the_api_with_the_headers_the_app_uses(client):
    r = _preflight(client, "http://localhost:5180", "POST", "authorization, content-type")
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5180"


def test_other_pages_and_unused_methods_and_headers_are_refused(client):
    assert "access-control-allow-origin" not in _preflight(client, "https://evil.example", "POST").headers
    assert _preflight(client, "http://localhost:5180", "TRACE").status_code == 400
    assert _preflight(client, "http://localhost:5180", "POST", "x-custom-header").status_code == 400
