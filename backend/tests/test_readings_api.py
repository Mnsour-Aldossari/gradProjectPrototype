"""GET /api/missions/{id}/readings: every reading, in order, placed as the detectors place them. The ROS 2 bridge
(ros2_ws/) pages through it, so a detector node fed from it must find what the mission runner found."""

from __future__ import annotations

from conftest import auth_headers, mission_body, wait_until_finished

from app.detection import Reading, SurveyContext, detect_adaptive
from app.simulation import DEMO_AREA
from app.simulation.geo import LocalFrame


def all_readings(client, headers, mission_id: int, page: int) -> list[dict]:
    readings: list[dict] = []
    while True:
        after = readings[-1]["id"] if readings else 0
        r = client.get(f"/api/missions/{mission_id}/readings?after_id={after}&limit={page}", headers=headers)
        assert r.status_code == 200, r.text
        if not r.json():
            return readings
        readings += r.json()


def test_pages_hold_every_reading_in_order_with_the_detectors_coordinates(client):
    sup = auth_headers(client, "supervisor")
    body = mission_body()
    mission_id = client.post("/api/missions", json=body, headers=sup).json()["id"]
    client.post(f"/api/missions/{mission_id}/start", json={"speed_factor": 0}, headers=sup)
    mission = wait_until_finished(client, mission_id, sup)

    readings = all_readings(client, auth_headers(client, "field"), mission_id, page=700)
    assert len(readings) == mission["stats"]["sensor_readings"] > 700
    assert [r["id"] for r in readings] == sorted({r["id"] for r in readings})
    assert [r["t_s"] for r in readings] == sorted(r["t_s"] for r in readings)
    frame = LocalFrame.centred_on(DEMO_AREA)
    assert all((r["x_m"], r["y_m"]) == frame.to_xy(r["lat"], r["lon"]) for r in readings)

    # A detector fed from these readings finds what the runner stored, to the stored rounding.
    context = SurveyContext(body["soil_type"], body["altitude_m"], body["speed_mps"], body["line_spacing_m"], 0.2)
    fields = ("t_s", "x_m", "y_m", "relative_alt_m", "md", "gpr_amp", "gpr_twt_ns")
    candidates = detect_adaptive([Reading(*(r[f] for f in fields)) for r in readings], context)
    stored = client.get(f"/api/missions/{mission_id}/detections?method=adaptive", headers=sup).json()
    assert candidates
    assert sorted(
        (c.category.value, c.n_hits, round(c.confidence, 3), *frame.to_latlon(c.x, c.y)) for c in candidates
    ) == sorted((d["category"], d["n_hits"], d["confidence"], d["lat"], d["lon"]) for d in stored)


def test_readings_need_a_mission_and_a_session(client):
    sup = auth_headers(client, "supervisor")
    mission_id = client.post("/api/missions", json=mission_body(), headers=sup).json()["id"]
    assert client.get(f"/api/missions/{mission_id}/readings", headers=sup).json() == []
    assert client.get("/api/missions/999/readings", headers=sup).status_code == 404
    assert client.get(f"/api/missions/{mission_id}/readings").status_code == 401
