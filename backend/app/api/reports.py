"""The mission report as a PDF, for the supervisor."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlmodel import select

from app.models import Detection, TelemetryPoint
from app.report import NoArabicFont, find_font, mission_report

from .deps import SessionDep, SupervisorUser
from .missions import get_mission_or_404

router = APIRouter(prefix="/api/missions", tags=["missions"])


@router.get(
    "/{mission_id}/report.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "The report (simulated data)"}},
)
def get_report(mission_id: int, request: Request, session: SessionDep, _: SupervisorUser) -> Response:
    """Mission, flight and sensor status, a map, the potential detections and their verification, as a PDF."""
    mission = get_mission_or_404(session, mission_id)
    settings = request.app.state.settings
    try:
        font = find_font(settings.report_font, settings.report_font_bold)
    except NoArabicFont as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    detections = session.exec(select(Detection).where(Detection.mission_id == mission_id)).all()
    track = session.exec(
        select(TelemetryPoint.lat, TelemetryPoint.lon)
        .where(TelemetryPoint.mission_id == mission_id)
        .order_by(TelemetryPoint.t_s)
    ).all()
    pdf = mission_report(mission, detections, track, font)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="mission-{mission_id}-report.pdf"'},
    )
