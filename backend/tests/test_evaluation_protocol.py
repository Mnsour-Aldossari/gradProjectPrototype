"""Mandatory tests T1-T3 from docs/EVALUATION_PROTOCOL.md (evaluation seeds, frozen parameters).

Results are on simulated data. If a test fails, the failure is reported as is;
the simulator and the frozen parameters are not changed to make it pass.
"""

import math

import pytest

from app.detection import Category, detect_adaptive, detect_baseline
from app.detection.evaluation import EvalCounts, evaluate
from app.evaluation.harness import simulate_scenario
from app.evaluation.protocol import EVALUATION_SEEDS, MATCH_RADIUS_M, SOIL_TYPES


@pytest.fixture(scope="module")
def evaluation():
    """Per scenario: truths, baseline candidates, adaptive candidates."""
    runs = []
    for soil in SOIL_TYPES:
        for seed in EVALUATION_SEEDS:
            run = simulate_scenario(soil, seed)
            runs.append((run, detect_baseline(run.readings), detect_adaptive(run.readings, run.context)))
    return runs


def near(candidates, obj):
    return [c for c in candidates if math.hypot(c.x - obj.x, c.y - obj.y) <= MATCH_RADIUS_M]


def test_T1_adaptive_raises_fewer_false_alarms_than_baseline(evaluation):
    baseline, adaptive = EvalCounts(), EvalCounts()
    for run, base_cands, adapt_cands in evaluation:
        baseline.add(evaluate(base_cands, run.truths, MATCH_RADIUS_M))
        adaptive.add(evaluate(adapt_cands, run.truths, MATCH_RADIUS_M))
    assert adaptive.fp < baseline.fp, (adaptive.to_dict(), baseline.to_dict())


def test_T2_low_metal_mines_are_found_by_radar(evaluation):
    total = reported = 0
    not_radar_driven = []
    for run, _, adapt_cands in evaluation:
        for obj in run.truths:
            if obj.kind != "low_metal_mine":
                continue
            total += 1
            hits = [c for c in near(adapt_cands, obj) if c.category != Category.CLUTTER]
            if hits:
                reported += 1
                not_radar_driven += [
                    (run.soil_type, run.seed, c.features)
                    for c in hits
                    if not (c.features["gpr_evidence"] >= 1 and c.features["md_evidence"] < 1)
                ]
    assert reported / total > 0.5, f"{reported}/{total} low-metal mines reported"
    assert not not_radar_driven, not_radar_driven


def test_T3_scrap_is_classified_as_likely_clutter(evaluation):
    with_candidate = clutter_only = 0
    for run, _, adapt_cands in evaluation:
        for obj in run.truths:
            if obj.kind != "scrap_metal":
                continue
            cands = near(adapt_cands, obj)
            if cands:
                with_candidate += 1
                clutter_only += all(c.category == Category.CLUTTER for c in cands)
    assert clutter_only / with_candidate > 0.5, f"{clutter_only}/{with_candidate} scrap objects clutter-only"
