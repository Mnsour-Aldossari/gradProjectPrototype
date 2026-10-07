"""Database engine setup. The same code runs on SQLite and PostgreSQL."""

from __future__ import annotations

import time

from sqlalchemy import Engine, event, exc, inspect, text
from sqlmodel import SQLModel, create_engine

from . import models  # noqa: F401  (registers the tables on SQLModel.metadata)

IDLE_PING_S = 60.0  # a pooled connection unused for longer is checked before it is used again


def make_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        return create_engine(database_url, connect_args={"check_same_thread": False, "timeout": 30})
    engine = create_engine(database_url)
    ping_after_idle(engine)
    return engine


def ping_after_idle(engine: Engine) -> None:
    """Before a pooled connection that sat unused for IDLE_PING_S is handed out, check that the server still has it,
    and connect again if not. A hosted PostgreSQL that sleeps when nobody uses it (Neon's free plan, after 5 minutes)
    drops its connections, and the first request after a pause would fail. A connection in steady use is not
    checked: each check is a round trip, which counts with a database far away (pool_pre_ping checks every time)."""

    @event.listens_for(engine, "checkin")
    def returned(dbapi_connection, record) -> None:
        if dbapi_connection is not None:
            record.info["idle_since"] = time.monotonic()

    @event.listens_for(engine, "checkout")
    def taken(dbapi_connection, record, proxy) -> None:
        idle_since = record.info.get("idle_since")
        if idle_since is None or time.monotonic() - idle_since <= IDLE_PING_S:
            return
        try:
            engine.dialect.do_ping(dbapi_connection)
        except Exception as e:
            # The pool connects again. A server that dropped this connection (asleep, restarted) dropped the others
            # in the pool too, so they are all replaced, as pool_pre_ping does.
            raise exc.InvalidatePoolError() from e


# Columns added after the first release, as (table, column, SQL type and default). create_all() makes new tables
# but leaves existing ones as they are, so a database from an older version gets these added here.
ADDED_COLUMNS = [
    ("missions", "uav_source", "VARCHAR NOT NULL DEFAULT 'simulated'"),
    ("missions", "takeoff_lat", "FLOAT"),
    ("missions", "takeoff_lon", "FLOAT"),
    ("missions", "landing_lat", "FLOAT"),
    ("missions", "landing_lon", "FLOAT"),
]


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
    _add_missing_columns(engine)


def _add_missing_columns(engine: Engine) -> None:
    tables = inspect(engine)
    for table, column, ddl in ADDED_COLUMNS:
        if column not in {c["name"] for c in tables.get_columns(table)}:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
