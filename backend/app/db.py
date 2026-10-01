"""Database engine setup. The same code runs on SQLite and PostgreSQL."""

from __future__ import annotations

from sqlalchemy import Engine
from sqlmodel import SQLModel, create_engine

from . import models  # noqa: F401  (registers the tables on SQLModel.metadata)


def make_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False, "timeout": 30} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
