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
    assert all(d["method"] == "baseline" and d["status"] == "pending" for d in detections)
    assert all("potential" in d["category_label"].lower() or d["category"] != "high" for d in detections)


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
