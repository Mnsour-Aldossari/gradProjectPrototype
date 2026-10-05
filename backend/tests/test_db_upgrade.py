"""Databases made by an older version get the columns added since (app/db.py)."""

from __future__ import annotations

import sqlite3

from sqlmodel import Session, select

from app.db import init_db, make_engine
from app.models import Mission

# The missions table as v1.2 created it, before uav_source.
OLD_MISSIONS = """
CREATE TABLE missions (
    id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, area JSON NOT NULL, path JSON NOT NULL,
    path_length_m FLOAT NOT NULL, altitude_m FLOAT NOT NULL, speed_mps FLOAT NOT NULL,
    line_spacing_m FLOAT NOT NULL, soil_type VARCHAR NOT NULL, scenario_seed INTEGER NOT NULL,
    status VARCHAR NOT NULL, progress FLOAT NOT NULL, battery_pct FLOAT, error VARCHAR,
    created_by INTEGER, created_at DATETIME NOT NULL, started_at DATETIME, completed_at DATETIME
)
"""


def test_old_database_gets_uav_source_and_keeps_its_missions(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.execute(OLD_MISSIONS)
        db.execute(
            "INSERT INTO missions VALUES (1, 'Old survey', '[]', '[]', 10, 1.5, 2, 2, 'dry_sand', 7,"
            " 'completed', 1, 80, NULL, NULL, '2026-10-01 10:00:00', NULL, NULL)"
        )

    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    init_db(engine)  # a second start finds the column and leaves it

    with Session(engine) as session:
        mission = session.exec(select(Mission)).one()
    assert (mission.name, mission.status, mission.uav_source) == ("Old survey", "completed", "simulated")


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
