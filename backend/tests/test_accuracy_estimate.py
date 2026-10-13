"""The accuracy estimate shown while planning: interpolation over the table, and the API that serves it."""

from __future__ import annotations

import json

import pytest
from conftest import auth_headers, mission_body

from app.detection.accuracy import ALTITUDES_M, SPACINGS_M, SPEEDS_MPS, TABLE_PATH, estimate
from app.evaluation.protocol import ESTIMATE_SEEDS, EVALUATION_SEEDS, TUNING_SEEDS


def small_table(tmp_path, found_at: dict) -> object:
    """A table over a 2x2x2 grid, 10 targets per cell, found as given per altitude."""
    rows = [
        {"soil": "dry_sand", "altitude_m": a, "speed_mps": s, "line_spacing_m": d, "surveys": 2, "targets": 10,
         "found": found_at[a], "false_alarms": 4, "low_metal": 4, "low_metal_found": 2}
        for a in (1.0, 2.0) for s in (1.0, 2.0) for d in (1.0, 2.0)
    ]  # fmt: skip
    path = tmp_path / "table.json"
    path.write_text(json.dumps({"method": "adaptive", "seeds": [3000, 3029], "survey_area_m2": 2000.0,
        "altitudes_m": [1.0, 2.0], "speeds_mps": [1.0, 2.0], "spacings_m": [1.0, 2.0], "rows": rows}))  # fmt: skip
    return path


def test_between_grid_points_the_counts_are_interpolated_and_outside_the_edge_is_used(tmp_path):
    path = small_table(tmp_path, {1.0: 8, 2.0: 4})
    e = estimate("dry_sand", 1.5, 1.5, 1.5, path)
    assert e.recall == pytest.approx(0.6)
    assert e.precision == pytest.approx(6 / 10)
    assert e.false_alarms_per_ha == pytest.approx(4 / 2 / 0.2)
    assert e.low_metal_recall == pytest.approx(0.5)
    assert estimate("dry_sand", 0.5, 1.0, 1.0, path).recall == pytest.approx(0.8)
    assert estimate("dry_sand", 5.0, 1.0, 1.0, path).recall == pytest.approx(0.4)
    assert estimate("wet_clay", 1.5, 1.5, 1.5, path) is None
    assert estimate("dry_sand", 1.5, 1.5, 1.5, tmp_path / "missing.json") is None


def test_the_estimate_seeds_are_neither_tuning_nor_evaluation_seeds():
    assert not set(ESTIMATE_SEEDS) & (set(TUNING_SEEDS) | set(EVALUATION_SEEDS))


@pytest.mark.skipif(not TABLE_PATH.exists(), reason="accuracy table not generated")
def test_the_table_covers_the_grid_and_flying_slower_with_closer_lanes_finds_more():
    for soil in ("dry_sand", "wet_clay", "mineralized_rocky"):
        standard = estimate(soil, 1.5, 2.0, 2.0)
        careful = estimate(soil, 1.5, 1.0, 1.0)
        assert careful.recall > standard.recall and careful.low_metal_recall > standard.low_metal_recall, soil
        assert standard.surveys == len(ESTIMATE_SEEDS)
    assert len(json.loads(TABLE_PATH.read_text())["rows"]) == 3 * len(ALTITUDES_M) * len(SPEEDS_MPS) * len(SPACINGS_M)


@pytest.mark.skipif(not TABLE_PATH.exists(), reason="accuracy table not generated")
def test_the_outline_check_and_the_api_give_the_estimate(client):
    supervisor = auth_headers(client, "admin")
    check = client.post("/api/missions/check", json=mission_body(altitude_m=1.0), headers=supervisor).json()
    assert check["accuracy"]["altitude_m"] == 1.0 and 0 < check["accuracy"]["recall"] <= 1
    field = auth_headers(client, "field")
    r = client.get("/api/accuracy", params={"soil_type": "wet_clay", "speed_mps": 1.0}, headers=field)
    assert r.status_code == 200 and r.json()["soil_type"] == "wet_clay"
    assert client.get("/api/accuracy", params={"altitude_m": 9}, headers=field).status_code == 422
    assert client.get("/api/accuracy").status_code == 401
    grid = client.get("/api/accuracy/grid", params={"soil_type": "dry_sand"}, headers=field).json()
    assert len(grid) == len(ALTITUDES_M) * len(SPEEDS_MPS) * len(SPACINGS_M)
