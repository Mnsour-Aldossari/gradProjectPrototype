from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlmodel import Session, func, select

from app.detection import FROZEN_PARAMS
from app.detection.context import condition_profile
from app.evaluation.protocol import EVALUATION_SEEDS, STANDARD_SURVEY
from app.models import Detection, Mission, SensorReading, TelemetryPoint, User, utcnow
from app.schemas import (
    CategoryCounts,
    ConditionProfileRead,
    MissionCreate,
    MissionHistory,
    MissionHistoryItem,
    MissionPage,
    MissionRead,
    MissionStatus,
    MissionStats,
    SoilType,
    StartRequest,
    TelemetryRead,
    VerificationCounts,
)
from app.simulation import plan_survey
from app.simulation.scenario import generate_scenario

from .deps import CurrentUser, SessionDep, SettingsDep, SupervisorUser
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


def mission_read(session: Session, mission: Mission, with_stats: bool = False) -> MissionRead:
    out = MissionRead.model_validate(mission)
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


@router.get("/search", response_model=MissionPage)
def search_missions(
    session: SessionDep,
    _: CurrentUser,
    q: str = Query("", max_length=100, description="Part of the mission name, case-insensitive"),
    status_: MissionStatus | None = Query(None, alias="status"),
    soil_type: SoilType | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> MissionPage:
    """Missions newest first, filtered by name, status and soil type, one page at a time."""
    query = select(Mission)
    if q.strip():
        query = query.where(func.lower(Mission.name).contains(q.strip().lower(), autoescape=True))
    if status_ is not None:
        query = query.where(Mission.status == status_)
    if soil_type is not None:
        query = query.where(Mission.soil_type == soil_type)
    total = session.exec(select(func.count()).select_from(query.subquery())).one()
    missions = session.exec(
        query.order_by(Mission.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return MissionPage(
        items=[mission_read(session, m) for m in missions], total=total, page=page, page_size=page_size
    )


@router.get("/history", response_model=MissionHistory)
def mission_history(session: SessionDep, _: CurrentUser) -> MissionHistory:
    """Finished missions (completed or failed) with potential-detection counts per category."""
    missions = session.exec(
        select(Mission).where(Mission.status.in_(("completed", "failed"))).order_by(Mission.id.desc())
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
        failed=sum(m.status == "failed" for m in missions),
    )


def _create(session: Session, body: MissionCreate, user: User) -> Mission:
    plan = plan_survey(body.area, body.line_spacing_m)
    width, height = plan.width_m, plan.height_m
    if not (MIN_SIDE_M <= width <= MAX_SIDE_M and MIN_SIDE_M <= height <= MAX_SIDE_M):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Survey area must be {MIN_SIDE_M:.0f}-{MAX_SIDE_M:.0f} m on each side (got {width:.0f} x {height:.0f} m)",
        )
    if plan.length_m > MAX_PATH_M:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Survey path would be {plan.length_m / 1000:.1f} km; increase line spacing or reduce the area",
        )
    seed = body.scenario_seed if body.scenario_seed is not None else secrets.randbelow(1_000_000)
    try:
        generate_scenario(plan.area_xy, body.soil_type, seed)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

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


def _start(request: Request, session: Session, mission: Mission, speed_factor: float) -> Mission:
    runner = request.app.state.runner
    if mission.status != "planned" or runner.is_running(mission.id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mission is already {mission.status}")
    source = make_source(mission, request.app.state.settings, speed_factor)
    mission.status = "running"
    mission.started_at = utcnow()
    session.add(mission)
    session.commit()
    session.refresh(mission)
    request.app.state.hub.publish(mission.id, mission_event(mission))
    runner.start(mission.id, source)
    return mission


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
    return mission_read(session, _start(request, session, mission, speed_factor))


@router.get("/{mission_id}", response_model=MissionRead)
def get_mission(mission_id: int, session: SessionDep, _: CurrentUser) -> MissionRead:
    return mission_read(session, get_mission_or_404(session, mission_id), with_stats=True)


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
    return mission_read(session, _start(request, session, mission, speed_factor))


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
