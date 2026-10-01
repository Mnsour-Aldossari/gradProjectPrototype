from conftest import auth_headers, mission_body, wait_until_finished


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_login_rejects_wrong_password(client):
    r = client.post("/api/auth/login", json={"username": "supervisor", "password": "wrong"})
    assert r.status_code == 401


def test_endpoints_require_a_token(client):
    assert client.get("/api/missions").status_code == 401
    assert client.get("/api/missions", headers={"Authorization": "Bearer forged.token"}).status_code == 401


def test_field_operator_cannot_create_missions(client):
    r = client.post("/api/missions", json=mission_body(), headers=auth_headers(client, "field"))
    assert r.status_code == 403


def test_create_mission_plans_the_survey_path(client):
    r = client.post("/api/missions", json=mission_body(), headers=auth_headers(client, "supervisor"))
    assert r.status_code == 201, r.text
    mission = r.json()
    assert mission["status"] == "planned"
    assert len(mission["path"]) >= 4
    assert mission["path_length_m"] > 0
    assert mission["estimated_duration_s"] == round(mission["path_length_m"] / mission["speed_mps"], 1)


def test_create_mission_rejects_bad_input(client):
    headers = auth_headers(client, "supervisor")
    tiny = [[24.1, 47.2], [24.1, 47.20005], [24.10005, 47.20005]]
    assert client.post("/api/missions", json=mission_body(area=tiny), headers=headers).status_code == 422
    assert client.post("/api/missions", json=mission_body(soil_type="lava"), headers=headers).status_code == 422
    assert client.post("/api/missions", json=mission_body(altitude_m=50), headers=headers).status_code == 422


def test_full_mission_run_stores_telemetry_readings_and_detections(client):
    sup = auth_headers(client, "supervisor")
    mission_id = client.post("/api/missions", json=mission_body(), headers=sup).json()["id"]

    r = client.post(f"/api/missions/{mission_id}/start", json={"speed_factor": 0}, headers=sup)
    assert r.status_code == 202, r.text

    mission = wait_until_finished(client, mission_id, sup)
    assert mission["status"] == "completed", mission["error"]
    assert mission["progress"] == 1.0
    stats = mission["stats"]
    assert stats["telemetry_points"] > 100
    assert stats["sensor_readings"] == stats["telemetry_points"]
    assert stats["detections"] >= 1

    telemetry = client.get(f"/api/missions/{mission_id}/telemetry", headers=sup).json()
    assert len(telemetry) == stats["telemetry_points"]
    assert telemetry[0]["battery_pct"] >= telemetry[-1]["battery_pct"]
    assert 1.0 < telemetry[0]["relative_alt_m"] < 2.0

    detections = client.get(f"/api/missions/{mission_id}/detections", headers=sup).json()
    assert len(detections) == stats["detections"]
    assert {d["method"] for d in detections} == {"baseline", "adaptive"}
    assert all(d["status"] == "pending" for d in detections)
    assert all("potential" in d["category_label"].lower() or d["category"] != "high" for d in detections)
    assert all("confirmed" not in d["explanation"].lower() for d in detections)

    adaptive = client.get(f"/api/missions/{mission_id}/detections?method=adaptive", headers=sup).json()
    assert adaptive and all(d["method"] == "adaptive" for d in adaptive)
    assert all("soil_type" in d["features"] for d in adaptive)


def test_live_adaptive_detections_match_the_offline_detector(client):
    """Detections built up during the flight equal a batch run over the whole survey."""
    from app.detection import detect_adaptive
    from app.evaluation.harness import simulate_scenario
    from app.simulation import DEMO_AREA

    sup = auth_headers(client, "supervisor")
    body = mission_body(speed_mps=2.0, line_spacing_m=2.0, soil_type="wet_clay", scenario_seed=77)
    mission_id = client.post("/api/missions", json=body, headers=sup).json()["id"]
    client.post(f"/api/missions/{mission_id}/start", json={"speed_factor": 0}, headers=sup)
    assert wait_until_finished(client, mission_id, sup)["status"] == "completed"
    live = client.get(f"/api/missions/{mission_id}/detections?method=adaptive", headers=sup).json()

    run = simulate_scenario("wet_clay", 77, {"area": DEMO_AREA, "altitude_m": 1.5, "speed_mps": 2.0, "line_spacing_m": 2.0})
    offline = detect_adaptive(run.readings, run.context)
    assert sorted((d["category"], d["n_hits"]) for d in live) == sorted((c.category.value, c.n_hits) for c in offline)


def test_condition_profile_endpoint(client):
    sup = auth_headers(client, "supervisor")
    mission_id = client.post("/api/missions", json=mission_body(soil_type="wet_clay"), headers=sup).json()["id"]
    profile = client.get(f"/api/missions/{mission_id}/profile", headers=sup).json()
    assert profile["soil_type"] == "wet_clay"
    assert profile["permittivity"] == 20.0
    assert profile["notes"]


def test_websocket_streams_snapshot_then_live_events(client):
    sup = auth_headers(client, "supervisor")
    mission_id = client.post("/api/missions", json=mission_body(), headers=sup).json()["id"]
    token = sup["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(f"/ws/missions/{mission_id}?token={token}") as ws:
        snapshot = ws.receive_json()
        assert snapshot["type"] == "snapshot" and snapshot["mission"]["status"] == "planned"
        client.post(f"/api/missions/{mission_id}/start", json={"speed_factor": 0}, headers=sup)
        seen = set()
        while True:
            event = ws.receive_json()
            seen.add(event["type"])
            if event["type"] == "mission" and event["status"] in ("completed", "failed"):
                assert event["status"] == "completed", event
                break
    assert {"telemetry", "detection_created", "mission"} <= seen


def test_websocket_rejects_bad_token(client):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/missions/1?token=forged") as ws:
            ws.receive_json()


def test_mission_cannot_start_twice(client):
    sup = auth_headers(client, "supervisor")
    mission_id = client.post("/api/missions", json=mission_body(), headers=sup).json()["id"]
    assert client.post(f"/api/missions/{mission_id}/start", json={"speed_factor": 0}, headers=sup).status_code == 202
    assert client.post(f"/api/missions/{mission_id}/start", json={"speed_factor": 0}, headers=sup).status_code == 409
    wait_until_finished(client, mission_id, sup)


def test_personnel_can_record_verification_outcome(client):
    sup = auth_headers(client, "supervisor")
    field = auth_headers(client, "field")
    mission_id = client.post("/api/missions", json=mission_body(), headers=sup).json()["id"]
    client.post(f"/api/missions/{mission_id}/start", json={"speed_factor": 0}, headers=sup)
    wait_until_finished(client, mission_id, sup)
    detection = client.get(f"/api/missions/{mission_id}/detections", headers=field).json()[0]
    field_user_id = client.get("/api/auth/me", headers=field).json()["id"]

    r = client.patch(
        f"/api/detections/{detection['id']}", json={"status": "false_alarm", "notes": "Tin can"}, headers=field
    )
    assert r.status_code == 200
    assert r.json()["status"] == "false_alarm"
    assert r.json()["verified_by"] == field_user_id
    assert r.json()["verified_at"].endswith("Z")

    r = client.patch(f"/api/detections/{detection['id']}", json={"status": "pending"}, headers=field)
    assert r.json()["verified_by"] is None

    assert client.patch(f"/api/detections/{detection['id']}", json={"status": "mine"}, headers=field).status_code == 422


def test_evaluation_report_is_marked_simulated_and_lists_known_limitations(client):
    assert client.get("/api/evaluation").status_code == 401
    r = client.get("/api/evaluation", headers=auth_headers(client, "field"))
    assert r.status_code == 200
    report = r.json()
    assert report["simulated"] is True and "simulated data" in report["notice"]
    assert {s["key"] for s in report["soils"]} == {"dry_sand", "wet_clay", "mineralized_rocky", "all"}
    assert report["protocol"]["evaluation_seeds"] == [2000, 2029]
    assert len(report["limitations"]) == 4
    assert "confirmed mine" not in r.text.lower()


def test_demo_scenario_gives_the_same_detections_every_run(client):
    sup = auth_headers(client, "supervisor")
    assert client.post("/api/missions/demo", headers=auth_headers(client, "field")).status_code == 403

    def run_once():
        mission = client.post("/api/missions/demo", json={"speed_factor": 0}, headers=sup).json()
        assert mission["scenario_seed"] == 2000 and mission["soil_type"] == "dry_sand"
        assert wait_until_finished(client, mission["id"], sup)["status"] == "completed"
        detections = client.get(f"/api/missions/{mission['id']}/detections", headers=sup).json()
        return sorted(
            (d["method"], d["category"], round(d["lat"], 7), round(d["lon"], 7), d["n_hits"], d["confidence"])
            for d in detections
        )

    first, second = run_once(), run_once()
    assert first and first == second


def test_history_counts_potential_detections_per_category(client):
    sup = auth_headers(client, "supervisor")
    planned = client.post("/api/missions", json=mission_body(), headers=sup).json()["id"]
    done = client.post("/api/missions", json=mission_body(scenario_seed=12), headers=sup).json()["id"]
    client.post(f"/api/missions/{done}/start", json={"speed_factor": 0}, headers=sup)
    wait_until_finished(client, done, sup)
    detections = client.get(f"/api/missions/{done}/detections", headers=sup).json()
    reported = [d for d in detections if d["method"] == "adaptive" and d["category"] != "clutter"]
    client.patch(f"/api/detections/{reported[0]['id']}", json={"status": "false_alarm"}, headers=sup)

    history = client.get("/api/missions/history", headers=auth_headers(client, "field")).json()
    assert [i["mission"]["id"] for i in history["missions"]] == [done]  # planned missions are not history
    assert planned not in [i["mission"]["id"] for i in history["missions"]]
    item = history["missions"][0]
    for category in ("high", "suspect", "clutter"):
        expected = sum(d["method"] == "adaptive" and d["category"] == category for d in detections)
        assert item["adaptive"][category] == expected
    assert item["baseline_high"] == sum(d["method"] == "baseline" and d["category"] == "high" for d in detections)
    assert item["verification"]["false_alarm"] == 1
    assert item["verification"]["pending"] == len(reported) - 1
    assert history["completed"] == 1 and history["totals_adaptive"] == item["adaptive"]
