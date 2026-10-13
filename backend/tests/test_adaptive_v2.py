"""The version 2 adaptive detector: streaming equals batch, the height correction and the shallower limit for
reflectors without metal, on lone objects (no evaluation seeds)."""

from __future__ import annotations

import dataclasses

import pytest

from app.detection.adaptive import detect_adaptive
from app.detection.adaptive_v2 import AdaptiveDetectorV2, detect_adaptive_v2, gpr_gain, md_gain
from app.detection.context import SurveyContext
from app.detection.params_v2 import FROZEN_PARAMS_V2
from app.detection.types import Category, Reading
from app.evaluation.harness import simulate_scenario
from app.evaluation.protocol import STANDARD_SURVEY
from app.simulation import ObjectKind, Simulation, SimulationConfig, build_simulation
from app.simulation.scenario import BuriedObject
from app.simulation.sensors import SensorModel

PARAMS = FROZEN_PARAMS_V2


def lone(obj: BuriedObject, soil: str, altitude: float, seed: int = 7) -> tuple[list[Reading], SurveyContext]:
    cfg = SimulationConfig(soil_type=soil, seed=seed, **{**STANDARD_SURVEY, "altitude_m": altitude})
    generated = build_simulation(cfg)
    scenario = dataclasses.replace(generated.scenario, objects=(obj,))
    sim = Simulation(cfg, generated.plan, scenario, SensorModel(scenario, noise_seed=seed))
    readings = [Reading(f.t_s, f.x, f.y, f.alt_m, s.md, s.gpr_amp, s.gpr_twt_ns) for f, s in sim.samples()]
    return readings, SurveyContext(soil, cfg.altitude_m, cfg.speed_mps, cfg.line_spacing_m, cfg.dt_s)


def near(candidates, obj: BuriedObject):
    return [c for c in candidates if (c.x - obj.x) ** 2 + (c.y - obj.y) ** 2 <= 1.5**2]


@pytest.mark.parametrize("smooth", [False, True])
def test_reading_by_reading_gives_what_the_whole_survey_gives(smooth):
    run = simulate_scenario("wet_clay", 1003)
    params = dataclasses.replace(PARAMS, smooth=smooth)
    streaming = AdaptiveDetectorV2(run.context, params)
    for i in range(0, len(run.readings), 25):
        streaming.add(run.readings[i : i + 25])
        streaming.candidates()
    assert streaming.candidates() == detect_adaptive_v2(run.readings, run.context, params)


def test_the_gains_are_one_at_the_reference_height_and_the_metal_detector_grows_faster_lower():
    assert md_gain(0.75) / md_gain(1.5) > 6 and 1.4 < gpr_gain(0.75) / gpr_gain(1.5) < 1.6


def test_a_metal_mine_flown_low_is_high_priority_not_scrap():
    mine = BuriedObject(1, ObjectKind.METAL_MINE, 0.4, 0.3, depth_m=0.1, metal_mass=1.2, size_m=0.25, permittivity=None)
    readings, context = lone(mine, "mineralized_rocky", 0.75)
    v1 = near(detect_adaptive(readings, context), mine)
    v2 = near(detect_adaptive_v2(readings, context, PARAMS), mine)
    assert v1 and all(c.category == Category.CLUTTER for c in v1)  # version 1: "metal without body"
    assert any(c.category == Category.HIGH for c in v2)


def test_a_deep_stone_without_metal_is_clutter():
    stone = BuriedObject(1, ObjectKind.ROCK, 0.4, 0.3, depth_m=0.25, metal_mass=0.0, size_m=0.4, permittivity=8.0)
    readings, context = lone(stone, "dry_sand", 1.5)
    v1 = near(detect_adaptive(readings, context), stone)
    v2 = near(detect_adaptive_v2(readings, context, PARAMS), stone)
    assert any(c.category == Category.SUSPECT for c in v1)
    assert v2 and all(c.category == Category.CLUTTER for c in v2)
    assert any(c.features["reason"] == "deep_reflector" for c in v2)


def test_the_frozen_parameters_are_the_calibrations_best():
    import json
    from pathlib import Path

    best = json.loads((Path(__file__).resolve().parents[2] / "docs" / "calibration_result_v2.json").read_text())["best"]
    p = FROZEN_PARAMS_V2
    assert (p.k_md, p.k_gpr, p.body_ratio, p.max_reflector_depth_m, p.smooth) == (
        best["k_md"], best["k_gpr"], best["body_ratio"], best["max_reflector_depth_m"], best["smooth"])  # fmt: skip


def test_the_mission_profile_shows_the_live_detectors_thresholds(client):
    from conftest import auth_headers, mission_body

    sup = auth_headers(client, "supervisor")
    mission = client.post("/api/missions", json=mission_body(soil_type="dry_sand"), headers=sup).json()
    profile = client.get(f"/api/missions/{mission['id']}/profile", headers=sup).json()
    assert (profile["md_threshold_k"], profile["gpr_threshold_k"]) == (PARAMS.k_md / 0.5, PARAMS.k_gpr)  # v2: 6, 4
