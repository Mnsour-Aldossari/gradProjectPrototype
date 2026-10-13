"""A mission that fails to start is not left 'running', and the adaptive sync never deletes a verified detection."""

from __future__ import annotations

import pytest
from conftest import auth_headers, mission_body
from sqlmodel import Session

from app.api.runner import sync_adaptive
from app.models import Detection
from app.simulation.geo import LocalFrame


def _detection(mission_id: int, status: str) -> Detection:
    return Detection(
        mission_id=mission_id,
        method="adaptive",
        lat=30.0,
        lon=31.0,
        category="clutter",
        confidence=0.5,
        peak_md=0.0,
        peak_gpr=0.0,
        n_hits=1,
        explanation="",
        status=status,
    )


def _mission(client) -> tuple[int, dict]:
    sup = auth_headers(client, "admin")
    return client.post("/api/missions", json=mission_body(), headers=sup).json()["id"], sup


def test_a_start_that_fails_leaves_the_mission_planned(client, monkeypatch):
    mission_id, sup = _mission(client)

    def boom(*args, **kwargs):
        raise RuntimeError("could not start")

    monkeypatch.setattr(client.app.state.runner, "start", boom)
    with pytest.raises(RuntimeError):
        client.post(f"/api/missions/{mission_id}/start", json={"speed_factor": 0}, headers=sup)
    shown = client.get(f"/api/missions/{mission_id}", headers=sup).json()
    assert shown["status"] == "planned"
    assert shown["started_at"] is None


def test_sync_removes_a_stale_pending_detection_and_keeps_a_verified_one(client):
    mission_id, _ = _mission(client)
    engine = client.app.state.engine
    with Session(engine) as session:
        pending, verified = _detection(mission_id, "pending"), _detection(mission_id, "confirmed_by_team")
        session.add_all([pending, verified])
        session.commit()
        pending_id, verified_id = pending.id, verified.id

    events = sync_adaptive(engine, mission_id, LocalFrame(30.0, 31.0), [], match_radius_m=1.0)

    assert events == [{"type": "detection_removed", "id": pending_id}]
    with Session(engine) as session:
        assert session.get(Detection, pending_id) is None
        assert session.get(Detection, verified_id) is not None


def test_a_detection_verified_while_the_sync_runs_is_not_deleted(client):
    mission_id, _ = _mission(client)
    engine = client.app.state.engine
    with Session(engine) as session:
        row = _detection(mission_id, "pending")
        session.add(row)
        session.commit()
        row_id = row.id

    class VerifiedMeanwhile:
        """The frame is asked for positions after the sync has read the rows: a supervisor verifies the row then."""

        def to_xy(self, lat: float, lon: float):
            with Session(engine) as other:
                stored = other.get(Detection, row_id)
                stored.status = "confirmed_by_team"
                other.add(stored)
                other.commit()
            return (0.0, 0.0)

    events = sync_adaptive(engine, mission_id, VerifiedMeanwhile(), [], match_radius_m=1.0)

    assert events == []
    with Session(engine) as session:
        assert session.get(Detection, row_id).status == "confirmed_by_team"
