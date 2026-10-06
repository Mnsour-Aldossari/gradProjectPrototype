"""Request and response bodies for the REST API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, computed_field, field_validator

from .detection import CATEGORY_LABELS, Category


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


UtcDatetime = Annotated[datetime, PlainSerializer(_iso_utc, return_type=str)]

SoilType = Literal["dry_sand", "wet_clay", "mineralized_rocky"]
DetectionStatus = Literal["pending", "confirmed_by_team", "false_alarm"]


class LoginRequest(BaseModel):
    username: str
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: str


class LoginResponse(BaseModel):
    token: str
    user: UserRead


class MissionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    area: list[tuple[float, float]] = Field(min_length=3, max_length=50, description="Polygon vertices as [lat, lon]")
    altitude_m: float = Field(1.5, ge=0.5, le=5.0, description="Sensor height above ground")
    speed_mps: float = Field(2.0, ge=0.5, le=5.0)
    line_spacing_m: float = Field(2.0, ge=0.5, le=5.0)
    soil_type: SoilType = "dry_sand"
    scenario_seed: int | None = Field(None, ge=0, le=2_147_483_647, description="Fixed seed for a repeatable scenario")

    @field_validator("area")
    @classmethod
    def _coordinates_in_range(cls, area: list[tuple[float, float]]) -> list[tuple[float, float]]:
        for lat, lon in area:
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("coordinates out of range")
        return area


class MissionStats(BaseModel):
    telemetry_points: int
    sensor_readings: int
    detections: int


class MissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    area: list[list[float]]
    path: list[list[float]]
    path_length_m: float
    altitude_m: float
    speed_mps: float
    line_spacing_m: float
    soil_type: str
    scenario_seed: int
    status: str
    uav_source: str
    takeoff_lat: float | None
    takeoff_lon: float | None
    progress: float
    battery_pct: float | None
    error: str | None
    created_by: int | None
    created_at: UtcDatetime
    started_at: UtcDatetime | None
    completed_at: UtcDatetime | None
    # While running: surveying, paused, returning or landing. Not stored; the mission runner knows it.
    phase: str | None = None
    stats: MissionStats | None = None

    @computed_field
    @property
    def estimated_duration_s(self) -> float:
        return round(self.path_length_m / self.speed_mps, 1)


class CategoryCounts(BaseModel):
    high: int = 0
    suspect: int = 0
    clutter: int = 0


class VerificationCounts(BaseModel):
    """Verification status of the reported (high + suspect) adaptive detections."""

    pending: int = 0
    confirmed_by_team: int = 0
    false_alarm: int = 0


class MissionHistoryItem(BaseModel):
    mission: MissionRead
    adaptive: CategoryCounts
    verification: VerificationCounts
    baseline_high: int


class MissionHistory(BaseModel):
    missions: list[MissionHistoryItem]
    totals_adaptive: CategoryCounts
    totals_verification: VerificationCounts
    completed: int
    stopped: int
    failed: int


class TakeoffRequest(BaseModel):
    """PX4's takeoff point; null for both: the first point of the survey path."""

    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)


class ControlRequest(BaseModel):
    action: Literal["pause", "resume", "return", "land"]


class StartRequest(BaseModel):
    speed_factor: float | None = Field(
        None, ge=0, le=100, description="1 = real time, 10 = ten times faster, 0 = as fast as possible"
    )
    uav_source: Literal["simulated", "px4"] | None = Field(
        None, description="What flies the survey: the built-in simulator, or PX4 over MAVLink (real time)"
    )


class TelemetryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    t_s: float
    lat: float
    lon: float
    alt_msl_m: float
    relative_alt_m: float
    heading_deg: float
    ground_speed_mps: float
    battery_pct: float
    waypoint_seq: int


class DetectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mission_id: int
    method: str
    lat: float
    lon: float
    category: str
    confidence: float
    peak_md: float
    peak_gpr: float
    est_depth_m: float | None
    n_hits: int
    explanation: str
    features: dict
    status: str
    notes: str | None
    verified_by: int | None
    verified_at: UtcDatetime | None
    created_at: UtcDatetime

    @computed_field
    @property
    def category_label(self) -> str:
        try:
            return CATEGORY_LABELS[Category(self.category)]
        except ValueError:
            return self.category


class ConditionProfileRead(BaseModel):
    soil_type: str
    soil_label: str
    permittivity: float
    md_reliability: float
    gpr_reliability: float
    md_threshold_k: float
    gpr_threshold_k: float
    radar_trusted: bool
    background_window_m: float
    link_radius_m: float
    notes: list[str]


class DetectionUpdate(BaseModel):
    status: DetectionStatus
    notes: str | None = Field(None, max_length=500)
