"""WebSocket hub: pushes live mission events (telemetry, detections, alerts, status) to the dashboard."""

from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlmodel import Session, func, select

from app.models import Detection, Mission, SensorReading, TelemetryPoint, User
from app.schemas import DetectionRead
from app.security import decode_token

router = APIRouter(tags=["live"])

QUEUE_SIZE = 2000


class Hub:
    def __init__(self) -> None:
        self._subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None

    def subscribe(self, mission_id: int) -> asyncio.Queue:
        self._loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers[mission_id].add(queue)
        return queue

    def unsubscribe(self, mission_id: int, queue: asyncio.Queue) -> None:
        self._subscribers[mission_id].discard(queue)

    def has_subscribers(self, mission_id: int) -> bool:
        return bool(self._subscribers.get(mission_id))

    def publish(self, mission_id: int, event: dict) -> None:
        """Safe to call from the event loop or from a worker thread (sync endpoints)."""
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if self._loop is not None and running is not self._loop:
            self._loop.call_soon_threadsafe(self._deliver, mission_id, event)
        else:
            self._deliver(mission_id, event)

    def _deliver(self, mission_id: int, event: dict) -> None:
        for queue in list(self._subscribers.get(mission_id, ())):
            with contextlib.suppress(asyncio.QueueFull):  # a stalled client misses events, others don't wait
                queue.put_nowait(event)


def detection_event(kind: str, detection: Detection) -> dict:
    return {"type": kind, "detection": DetectionRead.model_validate(detection).model_dump(mode="json")}


def _snapshot(session: Session, mission: Mission, user: User, runner) -> dict:
    from .missions import mission_read  # avoid import cycle

    detections = session.exec(select(Detection).where(Detection.mission_id == mission.id).order_by(Detection.id)).all()
    points = session.exec(
        select(TelemetryPoint).where(TelemetryPoint.mission_id == mission.id).order_by(TelemetryPoint.t_s)
    ).all()
    # When the survey lines began (first sensor reading), as in the live telemetry events.
    survey_start_s = session.exec(
        select(func.min(SensorReading.t_s)).where(SensorReading.mission_id == mission.id)
    ).one()
    return {
        "type": "snapshot",
        "mission": mission_read(session, mission, user, with_stats=True, runner=runner).model_dump(mode="json"),
        "detections": [DetectionRead.model_validate(d).model_dump(mode="json") for d in detections],
        "track": [[p.lat, p.lon] for p in points],
        "last_telemetry": None
        if not points
        else {
            "t_s": points[-1].t_s,
            "lat": points[-1].lat,
            "lon": points[-1].lon,
            "relative_alt_m": points[-1].relative_alt_m,
            "heading_deg": points[-1].heading_deg,
            "ground_speed_mps": points[-1].ground_speed_mps,
            "battery_pct": points[-1].battery_pct,
            "survey_start_s": survey_start_s,
            "paused_s": runner.paused_s(mission.id),
        },
    }


def _open(app, token: str, mission_id: int) -> tuple[dict | None, int]:
    """The snapshot for this user, or (None, the close code) if they may not see the mission. Runs in a worker
    thread: the database may be far away, and the event loop keeps the other live views moving meanwhile."""
    data = decode_token(token, app.state.settings.secret_key)
    with Session(app.state.engine) as session:
        user = session.get(User, data["sub"]) if data else None
        mission = session.get(Mission, mission_id) if user else None
        if mission is None:
            return None, 4401 if user is None else 4404
        return _snapshot(session, mission, user, app.state.runner), 0


@router.websocket("/ws/missions/{mission_id}")
async def mission_events(websocket: WebSocket, mission_id: int, token: str = Query(...)) -> None:
    app = websocket.app
    hub: Hub = app.state.hub
    queue = hub.subscribe(mission_id)  # before the snapshot, so no event falls in between
    sender: asyncio.Task | None = None
    try:
        snapshot, refused = await asyncio.to_thread(_open, app, token, mission_id)
        if snapshot is None:
            await websocket.close(code=refused)
            return
        await websocket.accept()

        async def forward() -> None:
            await websocket.send_json(snapshot)
            while True:
                await websocket.send_json(await queue.get())

        sender = asyncio.create_task(forward())
        while True:
            await websocket.receive_text()  # clients don't send anything; this detects disconnects
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(mission_id, queue)
        if sender is not None:
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await sender
