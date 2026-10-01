"""Runs missions in the background: consumes a TelemetrySource and stores the data."""

from __future__ import annotations

import asyncio
import logging
import math

from sqlalchemy import Engine
from sqlmodel import Session

from app.config import Settings
from app.detection import Candidate, Reading, detect_baseline
from app.models import Detection, Mission, SensorReading, TelemetryPoint, utcnow
from app.simulation import SimulationConfig
from app.simulation.geo import LocalFrame
from app.uav import SimulatedSource, TelemetryFrame, TelemetrySource
from app.uav.px4_mavlink_source import Px4MavlinkSource

logger = logging.getLogger(__name__)

FLUSH_ROWS = 50  # telemetry + sensor rows per database write


def simulation_config_for(mission: Mission) -> SimulationConfig:
    return SimulationConfig(
        area=tuple((p[0], p[1]) for p in mission.area),
        altitude_m=mission.altitude_m,
        speed_mps=mission.speed_mps,
        line_spacing_m=mission.line_spacing_m,
        soil_type=mission.soil_type,
        seed=mission.scenario_seed,
    )


def make_source(mission: Mission, settings: Settings, speed_factor: float) -> TelemetrySource:
    if settings.uav_source == "px4":
        return Px4MavlinkSource()
    return SimulatedSource(simulation_config_for(mission), speed_factor=speed_factor)


def _telemetry_row(mission_id: int, f: TelemetryFrame) -> TelemetryPoint:
    p = f.position
    return TelemetryPoint(
        mission_id=mission_id,
        t_s=p.time_boot_ms / 1000,
        lat=p.lat / 1e7,
        lon=p.lon / 1e7,
        alt_msl_m=p.alt / 1000,
        relative_alt_m=p.relative_alt / 1000,
        heading_deg=p.hdg / 100,
        ground_speed_mps=math.hypot(p.vx, p.vy) / 100,
        battery_pct=f.battery.battery_remaining,
        waypoint_seq=f.mission.seq,
    )


def _flush(engine: Engine, mission_id: int, rows: list, last: TelemetryFrame | None) -> None:
    with Session(engine) as session:
        session.add_all(rows)
        if last is not None:
            mission = session.get(Mission, mission_id)
            mission.progress = last.progress
            mission.battery_pct = last.battery.battery_remaining
            session.add(mission)
        session.commit()


def _detection_row(mission_id: int, frame: LocalFrame, c: Candidate) -> Detection:
    lat, lon = frame.to_latlon(c.x, c.y)
    return Detection(
        mission_id=mission_id,
        method=c.method,
        lat=lat,
        lon=lon,
        category=c.category.value,
        confidence=round(c.confidence, 3),
        peak_md=round(c.peak_md, 4),
        peak_gpr=round(c.peak_gpr, 4),
        est_depth_m=None if c.est_depth_m is None else round(c.est_depth_m, 3),
        n_hits=c.n_hits,
        explanation=c.explanation,
        features=dict(c.features),
    )


def _set_failed(engine: Engine, mission_id: int, error: str) -> None:
    with Session(engine) as session:
        mission = session.get(Mission, mission_id)
        mission.status = "failed"
        mission.error = error
        mission.completed_at = utcnow()
        session.add(mission)
        session.commit()


async def run_mission(engine: Engine, mission_id: int, source: TelemetrySource) -> None:
    with Session(engine) as session:
        area = session.get(Mission, mission_id).area
    frame = LocalFrame.centred_on(area)

    readings: list[Reading] = []
    rows: list = []
    last: TelemetryFrame | None = None
    try:
        async for f in source.frames():
            rows.append(_telemetry_row(mission_id, f))
            if f.sensor is not None:
                lat, lon = f.position.lat / 1e7, f.position.lon / 1e7
                t_s = f.position.time_boot_ms / 1000
                alt = f.position.relative_alt / 1000
                rows.append(
                    SensorReading(
                        mission_id=mission_id,
                        t_s=t_s,
                        lat=lat,
                        lon=lon,
                        relative_alt_m=alt,
                        md=f.sensor.md,
                        gpr_amp=f.sensor.gpr_amp,
                        gpr_twt_ns=f.sensor.gpr_twt_ns,
                    )
                )
                x, y = frame.to_xy(lat, lon)
                readings.append(Reading(t_s, x, y, alt, f.sensor.md, f.sensor.gpr_amp, f.sensor.gpr_twt_ns))
            last = f
            if len(rows) >= FLUSH_ROWS:
                _flush(engine, mission_id, rows, last)
                rows = []
        _flush(engine, mission_id, rows, last)

        candidates = detect_baseline(readings)
        with Session(engine) as session:
            session.add_all(_detection_row(mission_id, frame, c) for c in candidates)
            mission = session.get(Mission, mission_id)
            mission.status = "completed"
            mission.progress = 1.0
            mission.completed_at = utcnow()
            session.add(mission)
            session.commit()
    except asyncio.CancelledError:
        _set_failed(engine, mission_id, "Mission run was cancelled")
        raise
    except Exception as exc:
        logger.exception("Mission %s failed", mission_id)
        _set_failed(engine, mission_id, f"{type(exc).__name__}: {exc}")


class MissionRunner:
    """Keeps track of the background task for each running mission."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._tasks: dict[int, asyncio.Task] = {}

    def is_running(self, mission_id: int) -> bool:
        return mission_id in self._tasks

    def start(self, mission_id: int, source: TelemetrySource) -> None:
        task = asyncio.create_task(run_mission(self._engine, mission_id, source), name=f"mission-{mission_id}")
        self._tasks[mission_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(mission_id, None))

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
