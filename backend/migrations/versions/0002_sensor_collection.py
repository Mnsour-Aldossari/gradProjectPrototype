"""Sensor collection of each mission, apart from how its flight ended.

Missions flown before this keep sensor_collection empty (not recorded); their readings are counted. Planned ones
start as not_started.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("missions") as batch:
        batch.add_column(sa.Column("sensor_collection", sa.String(), nullable=True))
        batch.add_column(sa.Column("sensor_reading_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("sensor_coverage", sa.Float(), nullable=True))
        batch.add_column(sa.Column("sensor_note", sa.String(), nullable=True))
    op.execute("UPDATE missions SET sensor_collection = 'not_started' WHERE status = 'planned'")
    op.execute(
        "UPDATE missions SET sensor_reading_count ="
        " (SELECT COUNT(*) FROM sensor_readings WHERE sensor_readings.mission_id = missions.id)"
    )


def downgrade() -> None:
    with op.batch_alter_table("missions") as batch:
        batch.drop_column("sensor_note")
        batch.drop_column("sensor_coverage")
        batch.drop_column("sensor_reading_count")
        batch.drop_column("sensor_collection")
