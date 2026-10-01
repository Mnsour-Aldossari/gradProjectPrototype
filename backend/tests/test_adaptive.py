"""Adaptive detector: building blocks, streaming behaviour and single-object checks on fixed seeds."""

import dataclasses
import math

import pytest

from app.detection import AdaptiveDetector, Category, Reading, SurveyContext, detect_adaptive
from app.detection.context import condition_profile
from app.detection.params import FROZEN_PARAMS
from app.detection.threshold import RollingRobustScaler, robust_scores
from app.evaluation.harness import simulate_scenario
from app.simulation import DEMO_AREA, ObjectKind, Simulation, SimulationConfig, build_simulation
from app.simulation.scenario import BuriedObject
from app.simulation.sensors import SensorModel

MATCH_RADIUS_M = 1.5


# --- adaptive threshold -------------------------------------------------------------------------


def test_slow_background_drift_does_not_raise_scores_but_a_local_peak_does():
    values = [0.002 * i + (0.01 if i % 2 else 0.0) for i in range(300)]  # ramp + small noise
    values[150] += 0.5
    _, z = robust_scores(values, half_window=25, guard=5)
    assert z[150] > 10
    assert max(abs(v) for i, v in enumerate(z) if abs(i - 150) > 30) < 5


def test_guard_cells_keep_a_wide_object_from_hiding_itself():
    values = [0.01 * (i % 3) for i in range(200)]
    for i in range(96, 105):  # object spanning 9 samples
        values[i] += 1.0
    _, without_guard = robust_scores(values, half_window=12, guard=0)
    _, with_guard = robust_scores(values, half_window=12, guard=5)
    assert with_guard[100] > without_guard[100]
    assert with_guard[100] > 20


def test_streaming_scaler_matches_batch():
    values = [math.sin(i / 7) + (i % 5) * 0.01 for i in range(500)]
    scaler = RollingRobustScaler(half_window=20, guard=4)
    for start in range(0, 500, 37):
        scaler.extend(values[start : start + 37])
        scaler.scores()
    assert scaler.scores() == robust_scores(values, 20, 4)


def test_streaming_detector_matches_batch_detector():
    run = simulate_scenario("mineralized_rocky", 1000)  # tuning seed
    detector = AdaptiveDetector(run.context)
    for start in range(0, len(run.readings), 50):
        detector.add(run.readings[start : start + 50])
        detector.candidates()
    assert detector.candidates() == detect_adaptive(run.readings, run.context)


# --- condition profile ---------------------------------------------------------------------------


def test_condition_profile_adapts_to_soil_and_speed():
    def profile(soil, speed=2.0):
        return condition_profile(SurveyContext(soil, 1.5, speed, 2.0), FROZEN_PARAMS)

    assert profile("wet_clay").permittivity > profile("dry_sand").permittivity
    assert profile("dry_sand").radar_trusted
    assert profile("dry_sand", speed=1.0).half_window == 2 * profile("dry_sand", speed=2.0).half_window
    assert profile("dry_sand").link_radius_m == pytest.approx(2.5)
    assert any("permittivity 20" in n for n in profile("wet_clay").notes)


# --- single objects on fixed seeds ---------------------------------------------------------------


def single_object_candidates(obj: BuriedObject, soil: str, seed: int):
    cfg = SimulationConfig(area=DEMO_AREA, altitude_m=1.5, speed_mps=2.0, line_spacing_m=2.0, soil_type=soil, seed=seed)
    generated = build_simulation(cfg)
    scenario = dataclasses.replace(generated.scenario, objects=(obj,))
    sim = Simulation(cfg, generated.plan, scenario, SensorModel(scenario, noise_seed=seed))
    readings = [Reading(fs.t_s, fs.x, fs.y, fs.alt_m, ss.md, ss.gpr_amp, ss.gpr_twt_ns) for fs, ss in sim.samples()]
    candidates = detect_adaptive(readings, SurveyContext(soil, 1.5, 2.0, 2.0))
    return [c for c in candidates if math.hypot(c.x - obj.x, c.y - obj.y) <= MATCH_RADIUS_M]


@pytest.mark.parametrize("seed", [501, 502, 503])
def test_lone_low_metal_mine_is_reported_through_radar(seed):
    obj = BuriedObject(1, ObjectKind.LOW_METAL_MINE, 1.0, 0.5, depth_m=0.07, metal_mass=0.006, size_m=0.11, permittivity=2.5)
    near = single_object_candidates(obj, "dry_sand", seed)
    reported = [c for c in near if c.category != Category.CLUTTER]
    assert reported, [(c.category, c.features) for c in near]
    for c in reported:
        assert c.features["gpr_evidence"] >= 1 and c.features["md_evidence"] < 1
        assert "potential" not in c.explanation.lower() or "confirmed" not in c.explanation.lower()


@pytest.mark.parametrize("seed", [501, 502, 503])
def test_lone_scrap_fragment_is_likely_clutter(seed):
    obj = BuriedObject(1, ObjectKind.SCRAP_METAL, 1.0, 0.5, depth_m=0.05, metal_mass=0.8, size_m=0.04, permittivity=None)
    near = single_object_candidates(obj, "dry_sand", seed)
    assert near, "scrap should still produce a (clutter) candidate"
    assert all(c.category == Category.CLUTTER for c in near), [(c.category, c.features) for c in near]


@pytest.mark.parametrize("seed", [501, 502, 503])
def test_lone_metal_mine_is_high_priority(seed):
    obj = BuriedObject(1, ObjectKind.METAL_MINE, 1.0, 0.5, depth_m=0.10, metal_mass=1.0, size_m=0.25, permittivity=None)
    near = single_object_candidates(obj, "dry_sand", seed)
    assert any(c.category == Category.HIGH for c in near), [(c.category, c.features) for c in near]


def test_explanations_never_claim_a_confirmed_mine():
    run = simulate_scenario("dry_sand", 1001)  # tuning seed
    for c in detect_adaptive(run.readings, run.context):
        assert "confirmed" not in c.explanation.lower()
        assert c.method == "adaptive"
        assert 0 <= c.confidence <= 1
