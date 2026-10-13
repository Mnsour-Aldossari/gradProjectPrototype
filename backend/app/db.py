"""Database engine setup and schema migrations (Alembic, backend/migrations/). The same code runs on SQLite and
PostgreSQL."""

from __future__ import annotations

import time
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, Engine, event, exc, inspect
from sqlmodel import create_engine

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


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
BASELINE = "0001"  # migrations/versions/0001_baseline.py: the tables as they were before migrations


def init_db(engine: Engine) -> None:
    """Bring the database to the newest schema with the migrations in backend/migrations/ (alembic upgrade head), on
    SQLite and PostgreSQL alike. A new database gets every migration. One made before migrations existed has its
    tables but no alembic_version: it is checked against the baseline and marked as being at it first; rows stay."""
    with engine.begin() as conn:
        config = _alembic_config(conn)
        tables = set(inspect(conn).get_table_names())
        if tables and "alembic_version" not in tables:
            _adopt(conn, config)
        command.upgrade(config, "head")


def _alembic_config(conn: Connection) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR).replace("%", "%%"))
    config.attributes["connection"] = conn  # migrations/env.py runs on it
    return config


def _pre_migration_columns() -> list[tuple[str, sa.Column]]:
    """Columns added before migrations existed (v1.3 to v1.5). Older versions made the tables with create_all() and
    added these at startup, so a database last opened by an older version lacks them."""
    return [
        ("missions", sa.Column("uav_source", sa.String(), nullable=False, server_default="simulated")),
        ("missions", sa.Column("takeoff_lat", sa.Float())),
        ("missions", sa.Column("takeoff_lon", sa.Float())),
        ("missions", sa.Column("landing_lat", sa.Float())),
        ("missions", sa.Column("landing_lon", sa.Float())),
    ]


def _adopt(conn: Connection, config: Config) -> None:
    """Mark a database made before migrations as being at the baseline, after checking it has every table and column
    the baseline makes. The columns older versions added at startup are added if missing; anything else missing
    stops the backend with the database unchanged."""
    have = _columns(conn)
    added = [(t, c) for t, c in _pre_migration_columns() if t in have and c.name not in have[t]]
    for table, column in added:
        have[table].add(column.name)
    missing = []
    for table, columns in _baseline_columns().items():
        if table not in have:
            missing.append(f"table {table}")
        else:
            missing += [f"{table}.{c}" for c in sorted(columns - have[table])]
    if missing:
        raise RuntimeError(
            "The database has tables but no alembic_version, and it lacks some of the baseline migration's: "
            f"{', '.join(missing)}. It was left unchanged; it does not look like a database made by this project."
        )
    ops = Operations(MigrationContext.configure(conn))
    for table, column in added:
        ops.add_column(table, column)
    command.stamp(config, BASELINE)


def _baseline_columns() -> dict[str, set[str]]:
    """The tables and columns the baseline migration makes, read back from a scratch in-memory SQLite database."""
    scratch = create_engine("sqlite://")
    with scratch.begin() as conn:
        command.upgrade(_alembic_config(conn), BASELINE)
        columns = _columns(conn)
    scratch.dispose()
    columns.pop("alembic_version", None)
    return columns


def _columns(conn: Connection) -> dict[str, set[str]]:
    tables = inspect(conn)
    return {t: {c["name"] for c in tables.get_columns(t)} for t in tables.get_table_names()}
