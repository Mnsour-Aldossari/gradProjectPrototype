"""Baseline: the tables of app/models.py as v1.8 has them, before the database had migrations.

A database made before this (by create_all() at startup, no alembic_version table) is checked against these tables
and marked as being at this revision instead of running it (app/db.py, _adopt).

Revision ID: 0001
Revises:
Create Date: 2026-10-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    op.create_table(
        "missions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("area", sa.JSON(), nullable=False),
        sa.Column("path", sa.JSON(), nullable=False),
        sa.Column("path_length_m", sa.Float(), nullable=False),
        sa.Column("altitude_m", sa.Float(), nullable=False),
        sa.Column("speed_mps", sa.Float(), nullable=False),
        sa.Column("line_spacing_m", sa.Float(), nullable=False),
        sa.Column("soil_type", sa.String(), nullable=False),
        sa.Column("scenario_seed", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("uav_source", sa.String(), nullable=False),
        sa.Column("takeoff_lat", sa.Float(), nullable=True),
        sa.Column("takeoff_lon", sa.Float(), nullable=True),
        sa.Column("landing_lat", sa.Float(), nullable=True),
        sa.Column("landing_lon", sa.Float(), nullable=True),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("battery_pct", sa.Float(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "detections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mission_id", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("peak_md", sa.Float(), nullable=False),
        sa.Column("peak_gpr", sa.Float(), nullable=False),
        sa.Column("est_depth_m", sa.Float(), nullable=True),
        sa.Column("n_hits", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.String(), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("verified_by", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["mission_id"], ["missions.id"]),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_detections_mission_id"), "detections", ["mission_id"], unique=False)

    op.create_table(
        "sensor_readings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mission_id", sa.Integer(), nullable=False),
        sa.Column("t_s", sa.Float(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("relative_alt_m", sa.Float(), nullable=False),
        sa.Column("md", sa.Float(), nullable=False),
        sa.Column("gpr_amp", sa.Float(), nullable=False),
        sa.Column("gpr_twt_ns", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["mission_id"], ["missions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sensor_readings_mission_id"), "sensor_readings", ["mission_id"], unique=False)

    op.create_table(
        "telemetry_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mission_id", sa.Integer(), nullable=False),
        sa.Column("t_s", sa.Float(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("alt_msl_m", sa.Float(), nullable=False),
        sa.Column("relative_alt_m", sa.Float(), nullable=False),
        sa.Column("heading_deg", sa.Float(), nullable=False),
        sa.Column("ground_speed_mps", sa.Float(), nullable=False),
        sa.Column("battery_pct", sa.Float(), nullable=False),
        sa.Column("waypoint_seq", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["mission_id"], ["missions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_telemetry_points_mission_id"), "telemetry_points", ["mission_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_telemetry_points_mission_id"), table_name="telemetry_points")
    op.drop_table("telemetry_points")
    op.drop_index(op.f("ix_sensor_readings_mission_id"), table_name="sensor_readings")
    op.drop_table("sensor_readings")
    op.drop_index(op.f("ix_detections_mission_id"), table_name="detections")
    op.drop_table("detections")
    op.drop_table("missions")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_table("users")
