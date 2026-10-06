"""Runs missions in the background: consumes a TelemetrySource, stores the data,
updates adaptive detections while the UAV flies, and pushes live events."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time

from sqlalchemy import Engine
from sqlmodel import Session, select

from app.config import Settings
from app.detection import AdaptiveDetector, Candidate, Category, Reading, SurveyContext, detect_baseline
from app.models import Detection, Mission, SensorReading, TelemetryPoint, utcnow
from app.simulation import SimulationConfig
from app.simulation.geo import LocalFrame
from app.uav import SimulatedSource, TelemetryFrame, TelemetrySource
from app.uav.control import Action, FlightControl, Phase
from app.uav.px4_docker import Px4Docker
from app.uav.px4_gazebo import Px4Gazebo
from app.uav.px4_mavlink_source import Px4Launcher, Px4MavlinkSource
from app.uav.px4_plan import default_takeoff

from .ws import Hub, detection_event

logger = logging.getLogger(__name__)

FLUSH_ROWS = 50  # telemetry + sensor rows per database write
DETECT_EVERY_FRAMES = 25  # re-run the adaptive detector every 5 s of flight
TELEMETRY_EVENT_INTERVAL_S = 0.1  # max live telemetry rate pushed to clients (wall clock)


def simulation_config_for(mission: Mission) -> SimulationConfig:
    return SimulationConfig(
        area=tuple((p[0], p[1]) for p in mission.area),
        altitude_m=mission.altitude_m,
        speed_mps=mission.speed_mps,
        line_spacing_m=mission.line_spacing_m,
        soil_type=mission.soil_type,
        seed=mission.scenario_seed,
    )


def survey_context_for(mission: Mission) -> SurveyContext:
    return SurveyContext(
        soil_type=mission.soil_type,
        altitude_m=mission.altitude_m,
        speed_mps=mission.speed_mps,
        line_spacing_m=mission.line_spacing_m,
        sample_period_s=simulation_config_for(mission).dt_s,
    )


def px4_launchers(settings: Settings, gazebo: bool) -> tuple[Px4Launcher | None, tuple[Px4Launcher, ...]]:
    """The PX4 SITL the backend starts at the takeoff point (Gazebo's window in WSL, or the headless Docker image),
    and the other one, stopped first so that only one PX4 answers."""
    window = Px4Gazebo(settings.px4_gazebo_distro, settings.px4_gazebo_dir) if settings.px4_manage_gazebo else None
    headless = Px4Docker() if settings.px4_manage_docker else None
    launcher, other = (window, headless) if gazebo else (headless, window)
    return launcher, () if other is None else (other,)


def make_source(mission: Mission, settings: Settings, speed_factor: float, gazebo: bool = False) -> TelemetrySource:
    """PX4 flies in real time, so speed_factor only applies to the simulator. gazebo: PX4 SITL with Gazebo's window
    (WSL) rather than the headless image."""
    if mission.uav_source == "px4":
        launcher, others = px4_launchers(settings, gazebo)
        if mission.takeoff_lat is not None:
            takeoff = (mission.takeoff_lat, mission.takeoff_lon)
        elif launcher is not None:
            takeoff = default_takeoff(mission.area, mission.path)  # PX4 SITL is moved there: what the map shows
        else:
            takeoff = None  # a vehicle that cannot be moved flies from where it is
        landing = None if mission.landing_lat is None else (mission.landing_lat, mission.landing_lon)
        return Px4MavlinkSource(
            simulation_config_for(mission),
            settings.px4_url,
            takeoff=takeoff,
            launcher=launcher,
            landing=landing,
            others=others,
        )
    return SimulatedSource(simulation_config_for(mission), speed_factor=speed_factor)


def mission_event(mission: Mission, phase: Phase | None = None) -> dict:
    """phase: what the UAV is doing while the mission runs (surveying, paused, returning, landing)."""
    return {
        "type": "mission",
        "status": mission.status,
        "phase": phase if mission.status == "running" else None,
        "uav_source": mission.uav_source,
        "progress": mission.progress,
        "battery_pct": mission.battery_pct,
        "error": mission.error,
    }


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


def _telemetry_event(f: TelemetryFrame, survey_start_s: float | None, paused_s: float = 0.0) -> dict:
    """survey_start_s: flight time of the first sensor reading. PX4 takes off and flies to the first lane before
    that, so the page times the rest of the survey from here, not from takeoff. paused_s: flight time spent
    paused by the supervisor, which does not count towards the survey's pace either."""
    p = f.position
    return {
        "type": "telemetry",
        "t_s": p.time_boot_ms / 1000,
        "survey_start_s": survey_start_s,
        "paused_s": paused_s,
        "lat": p.lat / 1e7,
        "lon": p.lon / 1e7,
        "relative_alt_m": p.relative_alt / 1000,
        "heading_deg": p.hdg / 100,
        "ground_speed_mps": math.hypot(p.vx, p.vy) / 100,
        "battery_pct": f.battery.battery_remaining,
        "waypoint_seq": f.mission.seq,
        "waypoint_total": f.mission.total,
        "progress": f.progress,
        "md": None if f.sensor is None else f.sensor.md,
        "gpr": None if f.sensor is None else f.sensor.gpr_amp,
    }


def _apply(row: Detection, frame: LocalFrame, c: Candidate) -> None:
    row.lat, row.lon = frame.to_latlon(c.x, c.y)
    row.method = c.method
    row.category = c.category.value
    row.confidence = round(c.confidence, 3)
    row.peak_md = round(c.peak_md, 4)
    row.peak_gpr = round(c.peak_gpr, 4)
    row.est_depth_m = None if c.est_depth_m is None else round(c.est_depth_m, 3)
    row.n_hits = c.n_hits
    row.explanation = c.explanation
    row.features = dict(c.features)


def _new_detection(mission_id: int, frame: LocalFrame, c: Candidate) -> Detection:
    row = Detection(
        mission_id=mission_id,
        method=c.method,
        lat=0,
        lon=0,
        category="",
        confidence=0,
        peak_md=0,
        peak_gpr=0,
        n_hits=0,
        explanation="",
    )
    _apply(row, frame, c)
    return row


def sync_adaptive(
    engine: Engine, mission_id: int, frame: LocalFrame, candidates: list[Candidate], match_radius_m: float
) -> list[dict]:
    """Make the stored adaptive detections match the latest candidates.

    Candidates are matched to stored detections by position so a detection keeps
    its id (and any verification already recorded) as more passes refine it.
    """
    events: list[dict] = []
    with Session(engine) as session:
        existing = list(
            session.exec(select(Detection).where(Detection.mission_id == mission_id, Detection.method == "adaptive"))
        )
        positions = {row.id: frame.to_xy(row.lat, row.lon) for row in existing}
        unclaimed = {row.id: row for row in existing}
        changed: list[tuple[str, Detection, str | None]] = []

        for c in sorted(candidates, key=lambda c: -c.confidence):
            best = min(
                unclaimed.values(),
                key=lambda row: math.dist(positions[row.id], (c.x, c.y)),
                default=None,
            )
            if best is not None and math.dist(positions[best.id], (c.x, c.y)) <= match_radius_m:
                del unclaimed[best.id]
                before = (best.category, best.confidence, best.n_hits)
                previous_category = best.category
                _apply(best, frame, c)
                if (best.category, best.confidence, best.n_hits) != before:
                    session.add(best)
                    changed.append(("detection_updated", best, previous_category))
            else:
                row = _new_detection(mission_id, frame, c)
                session.add(row)
                changed.append(("detection_created", row, None))

        removed = [row for row in unclaimed.values() if row.status == "pending"]
        for row in removed:
            session.delete(row)
        session.commit()

        for kind, row, previous_category in changed:
            session.refresh(row)
            events.append(detection_event(kind, row))
            if row.category == Category.HIGH and previous_category != Category.HIGH:
                events.append({**detection_event("alert", row), "message": "Potential detection - high priority"})
        events += [{"type": "detection_removed", "id": row.id} for row in removed]
    return events


def _flush(engine: Engine, mission_id: int, rows: list, last: TelemetryFrame | None) -> Mission | None:
    with Session(engine) as session:
        session.add_all(rows)
        mission = None
        if last is not None:
            mission = session.get(Mission, mission_id)
            mission.progress = last.progress
            mission.battery_pct = last.battery.battery_remaining
            session.add(mission)
        session.commit()
        if mission is not None:
            session.refresh(mission)
        return mission


def _set_failed(engine: Engine, mission_id: int, error: str) -> Mission:
    with Session(engine) as session:
        mission = session.get(Mission, mission_id)
        mission.status = "failed"
        mission.error = error
        mission.completed_at = utcnow()
        session.add(mission)
        session.commit()
        session.refresh(mission)
        return mission


async def run_mission(
    engine: Engine, hub: Hub, mission_id: int, source: TelemetrySource, control: FlightControl | None = None
) -> None:
    control = control or FlightControl()
    with Session(engine) as session:
        mission = session.get(Mission, mission_id)
        frame = LocalFrame.centred_on(mission.area)
        detector = AdaptiveDetector(survey_context_for(mission))
    match_radius = detector.profile.link_radius_m

    all_readings: list[Reading] = []
    pending_readings: list[Reading] = []
    rows: list = []
    last: TelemetryFrame | None = None
    frames_since_detect = 0
    last_telemetry_event = 0.0
    survey_start_s: float | None = None
    phase = control.phase
    try:
        # aclosing: a cancelled run still lets the source finish (PX4 returns to launch).
        async with contextlib.aclosing(source.frames()) as frames:
            async for f in frames:
                rows.append(_telemetry_row(mission_id, f))
                if control.phase != phase:
                    phase = control.phase
                    with Session(engine) as session:
                        hub.publish(mission_id, mission_event(session.get(Mission, mission_id), phase))
                if f.sensor is not None:
                    lat, lon = f.position.lat / 1e7, f.position.lon / 1e7
                    t_s = f.position.time_boot_ms / 1000
                    if survey_start_s is None:
                        survey_start_s = t_s
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
                    reading = Reading(t_s, x, y, alt, f.sensor.md, f.sensor.gpr_amp, f.sensor.gpr_twt_ns)
                    all_readings.append(reading)
                    pending_readings.append(reading)
                last = f

                now = time.monotonic()
                # While paused every frame goes out and is stored: the simulator sends one frame at rest, then
                # nothing, and the page (live or reloaded) must show the UAV stopped.
                paused = control.phase == "paused"
                if paused or now - last_telemetry_event >= TELEMETRY_EVENT_INTERVAL_S:
                    hub.publish(mission_id, _telemetry_event(f, survey_start_s, control.paused_s))
                    last_telemetry_event = now

                if len(rows) >= FLUSH_ROWS or (paused and rows):
                    mission = _flush(engine, mission_id, rows, last)
                    rows = []
                    hub.publish(mission_id, mission_event(mission, control.phase))

                frames_since_detect += 1
                if frames_since_detect >= DETECT_EVERY_FRAMES:
                    frames_since_detect = 0
                    detector.add(pending_readings)
                    pending_readings = []
                    for event in sync_adaptive(engine, mission_id, frame, detector.candidates(), match_radius):
                        hub.publish(mission_id, event)

        _flush(engine, mission_id, rows, last)
        if last is not None:
            hub.publish(mission_id, _telemetry_event(last, survey_start_s, control.paused_s))
        detector.add(pending_readings)
        for event in sync_adaptive(engine, mission_id, frame, detector.candidates(), match_radius):
            hub.publish(mission_id, event)

        with Session(engine) as session:
            baseline_rows = [_new_detection(mission_id, frame, c) for c in detect_baseline(all_readings)]
            session.add_all(baseline_rows)
            mission = session.get(Mission, mission_id)
            if control.stop_reason is None:
                mission.status = "completed"
                mission.progress = 1.0
            else:  # ended early by the supervisor: what was surveyed is kept
                mission.status = "stopped"
                mission.error = control.stop_reason
            mission.completed_at = utcnow()
            session.add(mission)
            session.commit()
            for row in baseline_rows:
                session.refresh(row)
                hub.publish(mission_id, detection_event("detection_created", row))
            session.refresh(mission)
            hub.publish(mission_id, mission_event(mission))
    except asyncio.CancelledError:
        hub.publish(mission_id, mission_event(_set_failed(engine, mission_id, "Mission run was cancelled")))
        raise
    except Exception as exc:
        logger.exception("Mission %s failed", mission_id)
        hub.publish(mission_id, mission_event(_set_failed(engine, mission_id, f"{type(exc).__name__}: {exc}")))


class MissionRunner:
    """Keeps track of the background task for each running mission."""

    def __init__(self, engine: Engine, hub: Hub) -> None:
        self._engine = engine
        self._hub = hub
        self._tasks: dict[int, asyncio.Task] = {}
        self._controls: dict[int, FlightControl] = {}
        self._px4: set[int] = set()

    def is_running(self, mission_id: int) -> bool:
        return mission_id in self._tasks

    def px4_mission(self) -> int | None:
        """The mission PX4 is flying, if any: there is one vehicle."""
        return next(iter(self._px4), None)

    def phase(self, mission_id: int) -> Phase | None:
        control = self._controls.get(mission_id)
        return None if control is None else control.phase

    def paused_s(self, mission_id: int) -> float:
        control = self._controls.get(mission_id)
        return 0.0 if control is None else control.paused_s

    def control(self, mission_id: int, action: Action) -> Phase:
        """Pass a supervisor command to the running mission. KeyError if it is not running; ControlRejected if the
        command does not apply now."""
        phase = self._controls[mission_id].request(action)
        with Session(self._engine) as session:
            self._hub.publish(mission_id, mission_event(session.get(Mission, mission_id), phase))
        return phase

    def start(self, mission_id: int, source: TelemetrySource, *, px4: bool = False) -> None:
        control = FlightControl()
        source.control = control
        task = asyncio.create_task(
            run_mission(self._engine, self._hub, mission_id, source, control), name=f"mission-{mission_id}"
        )
        self._tasks[mission_id] = task
        self._controls[mission_id] = control
        if px4:
            self._px4.add(mission_id)

        def done(_: asyncio.Task) -> None:
            self._tasks.pop(mission_id, None)
            self._controls.pop(mission_id, None)
            self._px4.discard(mission_id)

        task.add_done_callback(done)

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
