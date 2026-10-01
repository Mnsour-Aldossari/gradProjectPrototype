from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlmodel import Session, func, select

from app.models import Detection, Mission, SensorReading, TelemetryPoint, utcnow
from app.schemas import MissionCreate, MissionRead, MissionStats, StartRequest, TelemetryRead
from app.simulation import plan_survey
from app.simulation.scenario import generate_scenario

from .deps import CurrentUser, SessionDep, SettingsDep, SupervisorUser
from .runner import make_source

router = APIRouter(prefix="/api/missions", tags=["missions"])

MIN_SIDE_M = 20.0
MAX_SIDE_M = 300.0
MAX_PATH_M = 15_000.0


def get_mission_or_404(session: Session, mission_id: int) -> Mission:
    mission = session.get(Mission, mission_id)
    if mission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mission not found")
    return mission


def _count(session: Session, table: type, mission_id: int) -> int:
    return session.exec(select(func.count()).select_from(table).where(table.mission_id == mission_id)).one()


def _read(session: Session, mission: Mission, with_stats: bool = False) -> MissionRead:
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
    return [_read(session, m) for m in missions]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=MissionRead)
def create_mission(body: MissionCreate, session: SessionDep, user: SupervisorUser) -> MissionRead:
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
    return _read(session, mission)


@router.get("/{mission_id}", response_model=MissionRead)
def get_mission(mission_id: int, session: SessionDep, _: CurrentUser) -> MissionRead:
    return _read(session, get_mission_or_404(session, mission_id), with_stats=True)


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
    runner = request.app.state.runner
    if mission.status != "planned" or runner.is_running(mission_id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mission is already {mission.status}")
    speed_factor = body.speed_factor if body and body.speed_factor is not None else settings.default_speed_factor
    source = make_source(mission, settings, speed_factor)

    mission.status = "running"
    mission.started_at = utcnow()
    session.add(mission)
    session.commit()
    session.refresh(mission)
    runner.start(mission_id, source)
    return _read(session, mission)


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
