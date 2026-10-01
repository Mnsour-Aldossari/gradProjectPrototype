import math

import pytest

from app.detection import Category, Hit, Reading, detect_baseline
from app.detection.clustering import cluster_hits
from app.simulation import DEMO_AREA, ObjectKind, SimulationConfig, build_simulation

MATCH_RADIUS_M = 1.5


def simulate(soil: str, seed: int):
    sim = build_simulation(
        SimulationConfig(area=DEMO_AREA, altitude_m=1.5, speed_mps=2.0, line_spacing_m=2.0, soil_type=soil, seed=seed)
    )
    readings = [
        Reading(fs.t_s, fs.x, fs.y, fs.alt_m, ss.md, ss.gpr_amp, ss.gpr_twt_ns) for fs, ss in sim.samples()
    ]
    return sim.scenario, readings


def nearest(candidates, obj):
    return min(candidates, key=lambda c: math.hypot(c.x - obj.x, c.y - obj.y), default=None)


def reading(x, y, md=1.0, t=0.0):
    return Reading(t, x, y, 1.5, md, 0.0, 0.0)


def test_clustering_merges_nearby_hits_and_separates_distant_ones():
    hits = [Hit(reading(x, 0), 1.0) for x in (0.0, 0.4, 0.8)] + [Hit(reading(10.0, 0), 1.0)]
    clusters = cluster_hits(hits, link_radius_m=1.0)
    assert sorted(len(c.hits) for c in clusters) == [1, 3]


def test_cluster_center_is_score_weighted():
    clusters = cluster_hits([Hit(reading(0, 0), 3.0), Hit(reading(1, 0), 1.0)], link_radius_m=2.0)
    assert clusters[0].center == pytest.approx((0.25, 0.0))


@pytest.mark.parametrize("seed", [7, 11, 23])
def test_baseline_reports_metal_mines_as_potential_detections(seed):
    scenario, readings = simulate("dry_sand", seed)
    candidates = detect_baseline(readings)
    for obj in scenario.objects:
        if obj.kind == ObjectKind.METAL_MINE:
            c = nearest(candidates, obj)
            assert c is not None
            assert math.hypot(c.x - obj.x, c.y - obj.y) <= MATCH_RADIUS_M
            assert c.category == Category.HIGH
            assert c.method == "baseline"


@pytest.mark.parametrize("seed", [7, 11, 23])
def test_baseline_misses_low_metal_mines(seed):
    """Known limitation of a metal-detector-only rule; motivates using GPR."""
    scenario, readings = simulate("dry_sand", seed)
    candidates = detect_baseline(readings)
    for obj in scenario.objects:
        if obj.kind == ObjectKind.LOW_METAL_MINE:
            c = nearest(candidates, obj)
            assert c is None or math.hypot(c.x - obj.x, c.y - obj.y) > MATCH_RADIUS_M


def test_baseline_ignores_readings_below_threshold():
    assert detect_baseline([reading(0, 0, md=0.1), reading(0.4, 0, md=0.2)]) == []
