"""A hosted PostgreSQL that sleeps when nobody uses it (Neon) drops the connections the pool keeps. A connection
that sat unused for a while is checked before it is used again; one in steady use is not (a check is a round trip)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app import db
from app.db import make_engine, ping_after_idle


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'pool.db').as_posix()}")
    ping_after_idle(engine)
    yield engine
    engine.dispose()


def test_a_connection_dropped_while_idle_is_replaced(sqlite_engine, monkeypatch):
    with sqlite_engine.connect() as conn:
        dropped = conn.connection.dbapi_connection
    dropped.close()  # as a server does with the connection while it sits in the pool
    monkeypatch.setattr(db, "IDLE_PING_S", -1.0)  # idle long enough
    with sqlite_engine.connect() as conn:
        assert conn.execute(text("select 1")).scalar() == 1
        assert conn.connection.dbapi_connection is not dropped


def test_a_connection_in_steady_use_is_not_checked(sqlite_engine, monkeypatch):
    pings = []
    monkeypatch.setattr(sqlite_engine.dialect, "do_ping", lambda connection: pings.append(connection) or True)
    for _ in range(3):
        with sqlite_engine.connect() as conn:
            conn.execute(text("select 1"))
    assert pings == []
    monkeypatch.setattr(db, "IDLE_PING_S", -1.0)
    with sqlite_engine.connect() as conn:
        conn.execute(text("select 1"))
    assert len(pings) == 1


def test_postgresql_connection_closed_by_the_server_is_replaced(database_url, monkeypatch):
    if database_url.startswith("sqlite"):
        pytest.skip("needs a PostgreSQL server (TEST_DATABASE_URL)")
    engine, admin = make_engine(database_url), create_engine(database_url)
    try:
        with engine.connect() as conn:
            pid = conn.execute(text("select pg_backend_pid()")).scalar()
        with admin.connect() as conn:  # the server ends it, as Neon does when it goes to sleep
            assert conn.execute(text("select pg_terminate_backend(:pid)"), {"pid": pid}).scalar()
        monkeypatch.setattr(db, "IDLE_PING_S", -1.0)
        with engine.connect() as conn:
            assert conn.execute(text("select pg_backend_pid()")).scalar() != pid
    finally:
        engine.dispose()
        admin.dispose()
