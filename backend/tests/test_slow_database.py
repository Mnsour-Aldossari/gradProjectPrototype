"""A database far away answers each statement after a network round trip (93 ms to a hosted PostgreSQL in
Frankfurt from the development PC). The live view must not wait for it, or the UAV stands still on the page and
then jumps ahead. Here every statement and commit of the app's database waits 0.1 s."""

from __future__ import annotations

import contextlib
import threading
import time

from conftest import auth_headers, mission_body, wait_until_finished
from sqlalchemy import event

DELAY_S = 0.1


@contextlib.contextmanager
def slow_database(engine, delay_s: float = DELAY_S):
    """Slow inside the block. The listeners stay on the engine afterwards, without waiting: taking one off while a
    worker thread runs a statement would break SQLAlchemy's event dispatch."""
    slow = True

    def wait(*_args, **_kwargs) -> None:
        if slow:
            time.sleep(delay_s)

    event.listen(engine, "before_cursor_execute", wait)
    event.listen(engine, "commit", wait)
    try:
        yield
    finally:
        slow = False


def test_live_view_keeps_moving_while_the_database_is_slow(client):
    sup = auth_headers(client, "supervisor")
    mission_id = client.post("/api/missions", json=mission_body(), headers=sup).json()["id"]
    token = sup["Authorization"].removeprefix("Bearer ")
    arrivals = []  # (wall clock, flight time) of each telemetry event
    with client.websocket_connect(f"/ws/missions/{mission_id}?token={token}") as ws:
        ws.receive_json()  # the snapshot
        with slow_database(client.app.state.engine):
            # 10x: a frame every 20 ms, 50 rows to write every 0.5 s, and each write takes 0.5 s or more here.
            r = client.post(f"/api/missions/{mission_id}/start", json={"speed_factor": 10}, headers=sup)
            assert r.status_code == 202, r.text
            while len(arrivals) < 30:
                event_ = ws.receive_json()
                if event_["type"] == "telemetry":
                    arrivals.append((time.monotonic(), event_["t_s"]))
            client.post(f"/api/missions/{mission_id}/control", json={"action": "land"}, headers=sup)
    mission = wait_until_finished(client, mission_id, sup)
    assert mission["status"] == "stopped"

    gaps = [b - a for (a, _), (b, _) in zip(arrivals, arrivals[1:])]
    assert max(gaps) < 0.3, gaps  # one event every 0.1 s, as with a fast database
    steps = [b - a for (_, a), (_, b) in zip(arrivals, arrivals[1:])]
    assert max(steps) < 2 * min(steps), steps  # the UAV moves on evenly, without jumping ahead
    assert mission["stats"]["telemetry_points"] > 0  # what was flown is stored


def test_a_mission_started_twice_at_once_flies_once(client):
    sup = auth_headers(client, "supervisor")
    mission_id = client.post("/api/missions", json=mission_body(), headers=sup).json()["id"]
    answers = []

    def start() -> None:
        r = client.post(f"/api/missions/{mission_id}/start", json={"speed_factor": 0}, headers=sup)
        answers.append(r.status_code)

    # Both requests check the mission before either has written it as running (that takes a while here).
    with slow_database(client.app.state.engine):
        requests = [threading.Thread(target=start) for _ in range(2)]
        for request in requests:
            request.start()
        for request in requests:
            request.join()
    assert sorted(answers) == [202, 409]
    assert wait_until_finished(client, mission_id, sup)["status"] == "completed"


def test_a_failed_write_ends_the_mission_as_failed(client, monkeypatch):
    def full(*_args) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("app.api.runner._flush", full)
    sup = auth_headers(client, "supervisor")
    mission_id = client.post("/api/missions", json=mission_body(), headers=sup).json()["id"]
    client.post(f"/api/missions/{mission_id}/start", json={"speed_factor": 0}, headers=sup)
    mission = wait_until_finished(client, mission_id, sup)
    assert (mission["status"], mission["error"]) == ("failed", "OSError: disk full")
