"""Database engine setup. The same code runs on SQLite and PostgreSQL."""

from __future__ import annotations

from sqlalchemy import Engine, inspect, text
from sqlmodel import SQLModel, create_engine

from . import models  # noqa: F401  (registers the tables on SQLModel.metadata)


def make_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False, "timeout": 30} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


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
