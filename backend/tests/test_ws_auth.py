"""WebSocket sign-in: the token goes in the first message (not the URL), and a refusal reaches the client."""

from __future__ import annotations

import pytest
from conftest import auth_headers, mission_body
from starlette.websockets import WebSocketDisconnect

from app.api import ws as ws_module


def _mission_and_token(client):
    sup = auth_headers(client, "admin")
    mission_id = client.post("/api/missions", json=mission_body(), headers=sup).json()["id"]
    return mission_id, sup["Authorization"].removeprefix("Bearer ")


def test_token_in_the_first_message_opens_the_stream(client):
    mission_id, token = _mission_and_token(client)
    with client.websocket_connect(f"/ws/missions/{mission_id}") as ws:
        ws.send_json({"type": "auth", "token": token})
        assert ws.receive_json()["type"] == "snapshot"


def test_a_forged_token_in_the_first_message_is_closed_with_4401(client):
    mission_id, _ = _mission_and_token(client)
    with client.websocket_connect(f"/ws/missions/{mission_id}") as ws:
        ws.send_json({"type": "auth", "token": "forged"})
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 4401


def test_a_first_message_that_is_not_auth_is_closed_with_4401(client):
    mission_id, token = _mission_and_token(client)
    with client.websocket_connect(f"/ws/missions/{mission_id}") as ws:
        ws.send_text("not json")
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 4401
    with client.websocket_connect(f"/ws/missions/{mission_id}") as ws:
        ws.send_json({"token": token})  # right token, but no "type": "auth"
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 4401


def test_an_unknown_mission_is_closed_with_4404(client):
    _, token = _mission_and_token(client)
    with client.websocket_connect("/ws/missions/9999") as ws:
        ws.send_json({"type": "auth", "token": token})
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 4404


def test_no_first_message_times_out(client, monkeypatch):
    monkeypatch.setattr(ws_module, "AUTH_TIMEOUT_S", 0.2)
    mission_id, _ = _mission_and_token(client)
    with client.websocket_connect(f"/ws/missions/{mission_id}") as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 4401


def test_a_forged_token_subscribes_nothing(client):
    mission_id, _ = _mission_and_token(client)
    with client.websocket_connect(f"/ws/missions/{mission_id}") as ws:
        ws.send_json({"type": "auth", "token": "forged"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert not client.app.state.hub.has_subscribers(mission_id)


def test_the_token_in_the_url_still_works_for_older_clients(client):
    mission_id, token = _mission_and_token(client)
    with client.websocket_connect(f"/ws/missions/{mission_id}?token={token}") as ws:
        assert ws.receive_json()["type"] == "snapshot"
