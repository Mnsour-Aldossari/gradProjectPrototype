from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlmodel import select

from app.models import Detection, utcnow
from app.schemas import DetectionRead, DetectionUpdate

from .deps import CurrentUser, SessionDep
from .missions import get_mission_or_404
from .ws import detection_event

router = APIRouter(tags=["detections"])


@router.get("/api/missions/{mission_id}/detections", response_model=list[DetectionRead])
def list_detections(
    mission_id: int, session: SessionDep, _: CurrentUser, method: str | None = None
) -> list[Detection]:
    get_mission_or_404(session, mission_id)
    query = select(Detection).where(Detection.mission_id == mission_id)
    if method is not None:
        query = query.where(Detection.method == method)
    return list(session.exec(query.order_by(Detection.id)).all())


def _get_detection_or_404(session, detection_id: int) -> Detection:
    detection = session.get(Detection, detection_id)
    if detection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Detection not found")
    return detection


@router.get("/api/detections/{detection_id}", response_model=DetectionRead)
def get_detection(detection_id: int, session: SessionDep, _: CurrentUser) -> Detection:
    return _get_detection_or_404(session, detection_id)


@router.patch("/api/detections/{detection_id}", response_model=DetectionRead)
def update_detection(
    detection_id: int, body: DetectionUpdate, request: Request, session: SessionDep, user: CurrentUser
) -> Detection:
    """Record the verification outcome reported by personnel for a potential detection."""
    detection = _get_detection_or_404(session, detection_id)
    detection.status = body.status
    if body.notes is not None:
        detection.notes = body.notes
    if body.status == "pending":
        detection.verified_by = None
        detection.verified_at = None
    else:
        detection.verified_by = user.id
        detection.verified_at = utcnow()
    session.add(detection)
    session.commit()
    session.refresh(detection)
    # Let every open dashboard (e.g. the supervisor's) see the field verification.
    request.app.state.hub.publish(detection.mission_id, detection_event("detection_updated", detection))
    return detection
