"""The schema comes from the migrations in backend/migrations/ (app/db.py init_db). A database made before migrations
existed (by create_all() at startup, no alembic_version) keeps its rows, gets the columns added since, and is marked as
being at the baseline. These run on PostgreSQL too with TEST_DATABASE_URL set (the database_url fixture)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, select

from app.db import BASELINE, MIGRATIONS_DIR, _alembic_config, init_db, make_engine
from app.models import Mission
from scripts.reset_db import reset

TABLES = ["users", "missions", "telemetry_points", "sensor_readings", "detections"]
# The missions columns added after v1.2, before migrations existed.
ADDED_AFTER_V1_2 = ["uav_source", "takeoff_lat", "takeoff_lon", "landing_lat", "landing_lon"]
LOCAL_DB = Path(__file__).resolve().parents[1] / "uav.db"


def head() -> str:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(config).get_current_head()


def revision(engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def schema_differences(engine) -> list:
    """What differs between the database and app/models.py, as `alembic revision --autogenerate` would see it."""
    with engine.connect() as conn:
        return compare_metadata(MigrationContext.configure(conn), SQLModel.metadata)


def row_counts(engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {t: conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one() for t in TABLES}


def pre_migration_database(engine, *, version_1_2: bool) -> None:
    """A database as an older version left it, with a row in every table: the baseline's tables made without
    migrations (no alembic_version); with version_1_2, also without the missions columns added after v1.2."""
    with engine.begin() as conn:
        command.upgrade(_alembic_config(conn), BASELINE)
        conn.execute(text("DROP TABLE alembic_version"))
        for column in ADDED_AFTER_V1_2 if version_1_2 else []:
            conn.execute(text(f"ALTER TABLE missions DROP COLUMN {column}"))
    source = ("", "") if version_1_2 else (", uav_source", ", 'px4'")
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (id, username, full_name, role, password_hash)"
            " VALUES (1, 'old', 'Old supervisor', 'supervisor', 'x')"
        ))
        conn.execute(text(
            "INSERT INTO missions (id, name, area, path, path_length_m, altitude_m, speed_mps, line_spacing_m,"
            f" soil_type, scenario_seed, status, progress, created_by, created_at{source[0]})"
            " VALUES (1, 'Old survey', '[[24.1, 47.3]]', '[]', 10, 1.5, 2, 2, 'dry_sand', 7, 'completed', 1, 1,"
            f" '2026-10-01 10:00:00'{source[1]})"
        ))
        conn.execute(text(
            "INSERT INTO telemetry_points (mission_id, t_s, lat, lon, alt_msl_m, relative_alt_m, heading_deg,"
            " ground_speed_mps, battery_pct, waypoint_seq) VALUES (1, 0, 24.1, 47.3, 600, 1.5, 90, 2, 99, 0)"
        ))
        conn.execute(text(
            "INSERT INTO sensor_readings (mission_id, t_s, lat, lon, relative_alt_m, md, gpr_amp, gpr_twt_ns)"
            " VALUES (1, 0, 24.1, 47.3, 1.5, 0.2, 0.1, 3)"
        ))
        conn.execute(text(
            "INSERT INTO detections (mission_id, method, lat, lon, category, confidence, peak_md, peak_gpr, n_hits,"
            " explanation, features, status, created_at) VALUES (1, 'adaptive', 24.1, 47.3, 'high', 0.9, 1, 1, 3,"
            " 'old', '{}', 'confirmed_by_team', '2026-10-01 10:05:00')"
        ))


def test_a_new_database_is_built_by_the_migrations(database_url):
    engine = make_engine(database_url)
    init_db(engine)
    init_db(engine)  # a second start has nothing to do
    assert revision(engine) == head()
    assert schema_differences(engine) == []
    assert row_counts(engine) == dict.fromkeys(TABLES, 0)
    engine.dispose()


@pytest.mark.parametrize("version_1_2", [False, True], ids=["v1.8", "v1.2"])
def test_a_database_from_before_migrations_keeps_its_rows(database_url, version_1_2):
    engine = make_engine(database_url)
    pre_migration_database(engine, version_1_2=version_1_2)
    init_db(engine)
    init_db(engine)
    assert revision(engine) == head()
    assert schema_differences(engine) == []
    assert row_counts(engine) == dict.fromkeys(TABLES, 1)
    with Session(engine) as session:
        mission = session.exec(select(Mission)).one()
    # A v1.2 mission was flown by the simulator: the column added since says so; a later one keeps its value.
    expected_source = "simulated" if version_1_2 else "px4"
    assert (mission.name, mission.status, mission.uav_source, mission.takeoff_lat) == (
        "Old survey", "completed", expected_source, None)
    engine.dispose()


def test_a_copy_of_the_local_database_keeps_every_row(tmp_path):
    """backend/uav.db, the database the backend on this PC uses, copied first: the original is only read."""
    if not LOCAL_DB.exists():
        pytest.skip("no backend/uav.db on this PC")
    copy = tmp_path / "uav-copy.db"
    original, target = sqlite3.connect(f"file:{LOCAL_DB.as_posix()}?mode=ro", uri=True), sqlite3.connect(copy)
    try:
        original.backup(target)  # a consistent copy even while the backend has the database open
    finally:
        original.close()
        target.close()
    engine = make_engine(f"sqlite:///{copy.as_posix()}")
    before = row_counts(engine)
    init_db(engine)
    assert row_counts(engine) == before
    assert revision(engine) == head()
    assert schema_differences(engine) == []
    engine.dispose()


def test_a_database_that_is_not_ours_is_left_unchanged(database_url):
    engine = make_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE missions (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL)"))
    with pytest.raises(RuntimeError, match="table users"):
        init_db(engine)
    tables = inspect(engine)
    assert tables.get_table_names() == ["missions"]
    assert [c["name"] for c in tables.get_columns("missions")] == ["id", "name"]
    engine.dispose()


def test_reset_builds_the_database_again(database_url):
    engine = make_engine(database_url)
    pre_migration_database(engine, version_1_2=True)
    init_db(engine)
    reset(engine)
    assert revision(engine) == head()
    assert schema_differences(engine) == []
    assert row_counts(engine) == {"users": 2, "missions": 0, "telemetry_points": 0, "sensor_readings": 0,
                                  "detections": 0}
    engine.dispose()


def test_new_missions_fly_the_simulator_unless_told_otherwise(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'new.db').as_posix()}")
    init_db(engine)
    with Session(engine) as session:
        mission = Mission(
            name="New", area=[], path=[], path_length_m=1, altitude_m=1.5, speed_mps=2,
            line_spacing_m=2, soil_type="dry_sand", scenario_seed=1,
        )
        session.add(mission)
        session.commit()
        session.refresh(mission)
    assert mission.uav_source == "simulated"
