from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlmodel import Session, func, select

from app.detection import FROZEN_PARAMS
from app.detection.context import condition_profile
from app.evaluation.protocol import EVALUATION_SEEDS, STANDARD_SURVEY
from app.models import Detection, Mission, SensorReading, TelemetryPoint, User, utcnow
from app.schemas import (
    AreaCheck,
    AreaCheckResult,
    CategoryCounts,
    ConditionProfileRead,
    ControlRequest,
    MissionCreate,
    MissionHistory,
    MissionHistoryItem,
    MissionRead,
    MissionStats,
    StartRequest,
    TakeoffRequest,
    TelemetryRead,
    VerificationCounts,
)
from app.simulation import SurveyPlan, plan_survey
from app.simulation.geo import is_simple, polygon_area
from app.simulation.scenario import generate_scenario

from .deps import CurrentUser, SessionDep, SettingsDep, SupervisorUser
from app.uav.control import ControlRejected
from app.uav.px4_plan import Waypoint, default_takeoff, landing_check, takeoff_check
from app.uav.px4_mavlink_source import Px4Unavailable

from .runner import make_source, mission_event, survey_context_for

router = APIRouter(prefix="/api/missions", tags=["missions"])

MIN_SIDE_M = 20.0
MAX_SIDE_M = 300.0
MAX_PATH_M = 15_000.0

# Demo scenario, chosen by rule rather than by its result: the first evaluation seed and
# the default soil type, on the standard survey used in the evaluation.
DEMO_SEED = EVALUATION_SEEDS[0]
DEMO_SPEED_FACTOR = 20.0
DEMO_SCENARIO = {
    "name": f"Demo scenario (seed {DEMO_SEED}, dry sand)",
    "area": [list(p) for p in STANDARD_SURVEY["area"]],
    "altitude_m": STANDARD_SURVEY["altitude_m"],
    "speed_mps": STANDARD_SURVEY["speed_mps"],
    "line_spacing_m": STANDARD_SURVEY["line_spacing_m"],
    "soil_type": "dry_sand",
    "scenario_seed": DEMO_SEED,
}


def get_mission_or_404(session: Session, mission_id: int) -> Mission:
    mission = session.get(Mission, mission_id)
    if mission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mission not found")
    return mission


def _count(session: Session, table: type, mission_id: int) -> int:
    return session.exec(select(func.count()).select_from(table).where(table.mission_id == mission_id)).one()


def mission_read(session: Session, mission: Mission, with_stats: bool = False, runner=None) -> MissionRead:
    """runner: the MissionRunner, to add the phase of a running mission."""
    out = MissionRead.model_validate(mission)
    if len(mission.path) >= 2:
        takeoff = (
            [mission.takeoff_lat, mission.takeoff_lon]
            if mission.takeoff_lat is not None
            else list(default_takeoff(mission.area, mission.path))
        )
        out.takeoff_point = takeoff
        out.landing_point = [mission.landing_lat, mission.landing_lon] if mission.landing_lat is not None else takeoff
    if runner is not None and mission.status == "running":
        out.phase = runner.phase(mission.id)
    if with_stats:
        out.stats = MissionStats(
            telemetry_points=_count(session, TelemetryPoint, mission.id),
            sensor_readings=_count(session, SensorReading, mission.id),
            detections=_count(session, Detection, mission.id),
        )
    return out


@router.get("", response_model=list[MissionRead])
def list_missions(session: SessionDep, _: CurrentUser) -> list[MissionRead]:
    missions = session.exec(select(Mission).order_by(Mission.id.desc())).all()
    return [mission_read(session, m) for m in missions]


@router.get("/history", response_model=MissionHistory)
def mission_history(session: SessionDep, _: CurrentUser) -> MissionHistory:
    """Finished missions (completed, stopped or failed) with potential-detection counts per category."""
    missions = session.exec(
        select(Mission).where(Mission.status.in_(("completed", "stopped", "failed"))).order_by(Mission.id.desc())
    ).all()
    rows = session.exec(
        select(Detection.mission_id, Detection.method, Detection.category, Detection.status, func.count())
        .where(Detection.mission_id.in_([m.id for m in missions]))
        .group_by(Detection.mission_id, Detection.method, Detection.category, Detection.status)
    ).all()

    adaptive = {m.id: CategoryCounts() for m in missions}
    verification = {m.id: VerificationCounts() for m in missions}
    baseline_high = {m.id: 0 for m in missions}
    for mission_id, method, category, det_status, n in rows:
        if method == "baseline":
            if category == "high":
                baseline_high[mission_id] += n
            continue
        counts = adaptive[mission_id]
        setattr(counts, category, getattr(counts, category) + n)
        if category != "clutter":
            v = verification[mission_id]
            setattr(v, det_status, getattr(v, det_status) + n)

    items = [
        MissionHistoryItem(
            mission=mission_read(session, m),
            adaptive=adaptive[m.id],
            verification=verification[m.id],
            baseline_high=baseline_high[m.id],
        )
        for m in missions
    ]
    return MissionHistory(
        missions=items,
        totals_adaptive=CategoryCounts(
            high=sum(i.adaptive.high for i in items),
            suspect=sum(i.adaptive.suspect for i in items),
            clutter=sum(i.adaptive.clutter for i in items),
        ),
        totals_verification=VerificationCounts(
            pending=sum(i.verification.pending for i in items),
            confirmed_by_team=sum(i.verification.confirmed_by_team for i in items),
            false_alarm=sum(i.verification.false_alarm for i in items),
        ),
        completed=sum(m.status == "completed" for m in missions),
        stopped=sum(m.status == "stopped" for m in missions),
        failed=sum(m.status == "failed" for m in missions),
    )


def survey_problems(body: MissionCreate, seed: int) -> tuple[SurveyPlan, list[str]]:
    """The survey plan for an outline, and what would stop it being created (empty if nothing). The same rules
    for creating a mission and for checking an outline while it is drawn."""
    plan = plan_survey(body.area, body.line_spacing_m)
    problems: list[str] = []
    if not is_simple(plan.area_xy):
        problems.append("The outline crosses itself; move a corner so that no edges cross")
    width, height = plan.width_m, plan.height_m
    if not (MIN_SIDE_M <= width <= MAX_SIDE_M and MIN_SIDE_M <= height <= MAX_SIDE_M):
        problems.append(
            f"Survey area must be {MIN_SIDE_M:.0f}-{MAX_SIDE_M:.0f} m on each side (got {width:.0f} x {height:.0f} m)"
        )
    if len(plan.waypoints_xy) < 2:
        problems.append("The area is too narrow for a survey lane; make it wider")
    if plan.length_m > MAX_PATH_M:
        problems.append(f"Survey path would be {plan.length_m / 1000:.1f} km; increase line spacing or reduce the area")
    if not problems:
        try:
            generate_scenario(plan.area_xy, body.soil_type, seed)
        except ValueError as exc:
            problems.append(f"{str(exc).capitalize()}; make the area larger or less narrow")
    return plan, problems


def _create(session: Session, body: MissionCreate, user: User) -> Mission:
    seed = body.scenario_seed if body.scenario_seed is not None else secrets.randbelow(1_000_000)
    plan, problems = survey_problems(body, seed)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problems[0])

    mission = Mission(
        name=body.name,
        area=[list(p) for p in body.area],
        path=[list(p) for p in plan.waypoints_latlon],
        path_length_m=round(plan.length_m, 1),
        altitude_m=body.altitude_m,
        speed_mps=body.speed_mps,
        line_spacing_m=body.line_spacing_m,
        soil_type=body.soil_type,
        scenario_seed=seed,
        created_by=user.id,
    )
    session.add(mission)
    session.commit()
    session.refresh(mission)
    return mission


def _check_can_start(request: Request, mission: Mission) -> None:
    if mission.status != "planned" or request.app.state.runner.is_running(mission.id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mission is already {mission.status}")


async def _start(request: Request, session: Session, mission: Mission, speed_factor: float) -> Mission:
    """Start the mission with the source in mission.uav_source. PX4 is reached and given the survey first; if
    that fails the mission stays planned and the reason goes back to the user."""
    runner = request.app.state.runner
    _check_can_start(request, mission)
    source = make_source(mission, request.app.state.settings, speed_factor)
    px4 = mission.uav_source == "px4"
    if px4:
        busy = runner.px4_mission()
        if busy is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"PX4 is flying mission {busy}; wait until it has finished")
        try:
            await source.connect()
        except Px4Unavailable as e:
            session.rollback()  # the source choice is only kept for a mission that starts
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
        _check_can_start(request, mission)  # another request may have started it meanwhile
    mission.status = "running"
    mission.started_at = utcnow()
    session.add(mission)
    session.commit()
    session.refresh(mission)
    request.app.state.hub.publish(mission.id, mission_event(mission, "surveying"))
    runner.start(mission.id, source, px4=px4)
    return mission


@router.post("/check", response_model=AreaCheckResult)
def check_area(body: AreaCheck, _: SupervisorUser) -> AreaCheckResult:
    """Check a survey outline while it is drawn: the lanes it would get and what to change, without storing it."""
    plan, problems = survey_problems(body, body.scenario_seed if body.scenario_seed is not None else 0)
    return AreaCheckResult(
        ok=not problems,
        problems=problems,
        path=[list(p) for p in plan.waypoints_latlon],
        path_length_m=round(plan.length_m, 1),
        width_m=round(plan.width_m, 1),
        height_m=round(plan.height_m, 1),
        area_m2=round(polygon_area(plan.area_xy), 1),
        estimated_duration_s=round(plan.length_m / body.speed_mps, 1),
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=MissionRead)
def create_mission(body: MissionCreate, session: SessionDep, user: SupervisorUser) -> MissionRead:
    return mission_read(session, _create(session, body, user))


@router.post("/demo", status_code=status.HTTP_202_ACCEPTED, response_model=MissionRead)
async def run_demo_scenario(
    request: Request, session: SessionDep, user: SupervisorUser, body: StartRequest | None = None
) -> MissionRead:
    """Create and start the fixed demo scenario. Same seed and settings every time, so the same result."""
    mission = _create(session, MissionCreate(**DEMO_SCENARIO), user)
    speed_factor = body.speed_factor if body and body.speed_factor is not None else DEMO_SPEED_FACTOR
    mission = await _start(request, session, mission, speed_factor)  # always the simulator
    return mission_read(session, mission, runner=request.app.state.runner)


@router.get("/{mission_id}", response_model=MissionRead)
def get_mission(mission_id: int, request: Request, session: SessionDep, _: CurrentUser) -> MissionRead:
    mission = get_mission_or_404(session, mission_id)
    return mission_read(session, mission, with_stats=True, runner=request.app.state.runner)


@router.post("/{mission_id}/start", status_code=status.HTTP_202_ACCEPTED, response_model=MissionRead)
async def start_mission(
    mission_id: int,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    _: SupervisorUser,
    body: StartRequest | None = None,
) -> MissionRead:
    mission = get_mission_or_404(session, mission_id)
    speed_factor = body.speed_factor if body and body.speed_factor is not None else settings.default_speed_factor
    if body and body.uav_source is not None and mission.status == "planned":
        mission.uav_source = body.uav_source
    mission = await _start(request, session, mission, speed_factor)
    return mission_read(session, mission, runner=request.app.state.runner)


@router.put("/{mission_id}/takeoff", response_model=MissionRead)
def set_takeoff(mission_id: int, body: TakeoffRequest, session: SessionDep, _: SupervisorUser) -> MissionRead:
    """Where PX4 takes off for this mission, chosen on the map before the survey starts. It must be within PX4's
    900 m of the start of the survey. Both null: the start of the survey."""
    mission = get_mission_or_404(session, mission_id)
    if mission.status != "planned":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mission is already {mission.status}")
    if (body.lat is None) != (body.lon is None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give both lat and lon, or neither")
    if body.lat is not None:
        start = mission.path[0]
        reason = takeoff_check((body.lat, body.lon), [Waypoint(start[0], start[1], 0, 0)])
        if reason:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, reason)
    mission.takeoff_lat, mission.takeoff_lon = body.lat, body.lon
    session.add(mission)
    session.commit()
    session.refresh(mission)
    return mission_read(session, mission)


@router.put("/{mission_id}/landing", response_model=MissionRead)
def set_landing(mission_id: int, body: TakeoffRequest, session: SessionDep, _: SupervisorUser) -> MissionRead:
    """Where PX4 lands after the survey, chosen on the map before it starts (within 900 m of the end of the survey).
    Both null: back at the takeoff point."""
    mission = get_mission_or_404(session, mission_id)
    if mission.status != "planned":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mission is already {mission.status}")
    if (body.lat is None) != (body.lon is None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give both lat and lon, or neither")
    if body.lat is not None:
        end = mission.path[-1]
        reason = landing_check((body.lat, body.lon), [Waypoint(end[0], end[1], 0, 0)])
        if reason:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, reason)
    mission.landing_lat, mission.landing_lon = body.lat, body.lon
    session.add(mission)
    session.commit()
    session.refresh(mission)
    return mission_read(session, mission)


@router.post("/{mission_id}/control", status_code=status.HTTP_202_ACCEPTED, response_model=MissionRead)
def control_mission(
    mission_id: int, body: ControlRequest, request: Request, session: SessionDep, _: SupervisorUser
) -> MissionRead:
    """Pause or resume the survey, or end it early with a return home or a landing (the mission then becomes
    stopped once the UAV is down). Works for the simulator and PX4 alike."""
    mission = get_mission_or_404(session, mission_id)
    runner = request.app.state.runner
    try:
        runner.control(mission_id, body.action)
    except KeyError:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mission is {mission.status}, not flying") from None
    except ControlRejected as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return mission_read(session, mission, runner=runner)


@router.get("/{mission_id}/telemetry", response_model=list[TelemetryRead])
def get_telemetry(
    mission_id: int,
    session: SessionDep,
    _: CurrentUser,
    after_t: float = Query(-1.0, description="Only points with t_s greater than this"),
    limit: int = Query(5000, ge=1, le=20000),
) -> list[TelemetryPoint]:
    get_mission_or_404(session, mission_id)
    query = (
        select(TelemetryPoint)
        .where(TelemetryPoint.mission_id == mission_id, TelemetryPoint.t_s > after_t)
        .order_by(TelemetryPoint.t_s)
        .limit(limit)
    )
    return list(session.exec(query).all())


@router.get("/{mission_id}/profile", response_model=ConditionProfileRead)
def get_condition_profile(mission_id: int, session: SessionDep, _: CurrentUser) -> ConditionProfileRead:
    """How the adaptive detector is configured for this mission's survey conditions."""
    mission = get_mission_or_404(session, mission_id)
    profile = condition_profile(survey_context_for(mission), FROZEN_PARAMS)
    return ConditionProfileRead(
        soil_type=profile.soil_type,
        soil_label=profile.soil_label,
        permittivity=profile.permittivity,
        md_reliability=profile.md_reliability,
        gpr_reliability=profile.gpr_reliability,
        md_threshold_k=round(FROZEN_PARAMS.k_md / profile.md_reliability, 2),
        gpr_threshold_k=FROZEN_PARAMS.k_gpr,
        radar_trusted=profile.radar_trusted,
        background_window_m=FROZEN_PARAMS.background_window_m,
        link_radius_m=profile.link_radius_m,
        notes=list(profile.notes),
    )
