"""Alembic environment. The backend runs the migrations at startup on its own connection (app/db.py init_db);
`python -m alembic ...` from backend/ runs them on DATABASE_URL, or backend/uav.db when it is not set."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlmodel import SQLModel
from sqlmodel.sql.sqltypes import AutoString, UTCDateTime

from app.config import DEFAULT_DATABASE_URL
from app.db import make_engine

config = context.config


def render_item(type_, obj, autogen_context):
    """SQLModel's column types written as the plain SQLAlchemy types they store, so the migrations need no SQLModel
    import: str is a VARCHAR, and a datetime a DateTime with time zone (UTCDateTime converts the values only)."""
    if type_ == "type" and isinstance(obj, AutoString):
        return "sa.String()"
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=SQLModel.metadata,
        render_item=render_item,
        # SQLite cannot change most columns in place; batch mode copies the table instead.
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


connection = config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    if config.config_file_name is not None:
        fileConfig(config.config_file_name, disable_existing_loggers=False)
    engine = make_engine(os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL)
    with engine.begin() as conn:
        run(conn)
    engine.dispose()
