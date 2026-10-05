"""Database tables.

Only portable column types are used (JSON for polygons and feature maps), so
the schema works unchanged on SQLite and PostgreSQL.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp; SQLModel stores it as UTC on SQLite and PostgreSQL alike."""
    return datetime.now(UTC)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    full_name: str
    role: str  # "supervisor" | "field_operator"
    password_hash: str


class Mission(SQLModel, table=True):
    __tablename__ = "missions"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    area: list[list[float]] = Field(sa_column=Column(JSON, nullable=False))  # [[lat, lon], ...]
    path: list[list[float]] = Field(sa_column=Column(JSON, nullable=False))  # planned waypoints
    path_length_m: float
    altitude_m: float
    speed_mps: float
    line_spacing_m: float
    soil_type: str
    scenario_seed: int
    status: str = "planned"  # planned | running | completed | failed
    uav_source: str = "simulated"  # simulated | px4: what flew (or will fly) the survey
    progress: float = 0.0
    battery_pct: float | None = None
    error: str | None = None
    created_by: int | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TelemetryPoint(SQLModel, table=True):
    __tablename__ = "telemetry_points"

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key="missions.id", index=True)
    t_s: float
    lat: float
    lon: float
    alt_msl_m: float
    relative_alt_m: float
    heading_deg: float
    ground_speed_mps: float
    battery_pct: float
    waypoint_seq: int


class SensorReading(SQLModel, table=True):
    __tablename__ = "sensor_readings"

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key="missions.id", index=True)
    t_s: float
    lat: float
    lon: float
    relative_alt_m: float
    md: float
    gpr_amp: float
    gpr_twt_ns: float


class Detection(SQLModel, table=True):
    """A potential detection. Never a confirmed mine until verified by trained personnel."""

    __tablename__ = "detections"

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key="missions.id", index=True)
    method: str  # "baseline" | "adaptive"
    lat: float
    lon: float
    category: str  # high | suspect | clutter
    confidence: float
    peak_md: float
    peak_gpr: float
    est_depth_m: float | None = None
    n_hits: int
    explanation: str
    features: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    status: str = "pending"  # pending | confirmed_by_team | false_alarm
    notes: str | None = None
    verified_by: int | None = Field(default=None, foreign_key="users.id")
    verified_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
