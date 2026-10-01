"""Runs simulated surveys through both detectors and scores them against ground truth."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.detection import BaselineConfig, detect_baseline
from app.detection.adaptive import detect_adaptive
from app.detection.context import SurveyContext
from app.detection.evaluation import EvalCounts, TruthObject, evaluate
from app.detection.params import FROZEN_PARAMS, AdaptiveParams
from app.detection.types import Reading
from app.simulation import SimulationConfig, build_simulation

from .protocol import MATCH_RADIUS_M, STANDARD_SURVEY

METHODS = ("baseline", "adaptive")


@dataclass(frozen=True)
class ScenarioRun:
    soil_type: str
    seed: int
    context: SurveyContext
    truths: tuple[TruthObject, ...]
    readings: tuple[Reading, ...]


def simulate_scenario(soil_type: str, seed: int, survey: dict = STANDARD_SURVEY) -> ScenarioRun:
    cfg = SimulationConfig(soil_type=soil_type, seed=seed, **survey)
    sim = build_simulation(cfg)
    readings = tuple(
        Reading(fs.t_s, fs.x, fs.y, fs.alt_m, ss.md, ss.gpr_amp, ss.gpr_twt_ns) for fs, ss in sim.samples()
    )
    truths = tuple(TruthObject(o.x, o.y, o.kind.value, o.is_target) for o in sim.scenario.objects)
    context = SurveyContext(
        soil_type=soil_type,
        altitude_m=cfg.altitude_m,
        speed_mps=cfg.speed_mps,
        line_spacing_m=cfg.line_spacing_m,
        sample_period_s=cfg.dt_s,
    )
    return ScenarioRun(soil_type, seed, context, truths, readings)


def run_methods(
    run: ScenarioRun,
    baseline: BaselineConfig = BaselineConfig(),
    adaptive: AdaptiveParams = FROZEN_PARAMS,
) -> dict[str, EvalCounts]:
    return {
        "baseline": evaluate(detect_baseline(run.readings, baseline), run.truths, MATCH_RADIUS_M),
        "adaptive": evaluate(detect_adaptive(run.readings, run.context, adaptive), run.truths, MATCH_RADIUS_M),
    }


def evaluate_seeds(
    soils: Iterable[str],
    seeds: Iterable[int],
    baseline: BaselineConfig = BaselineConfig(),
    adaptive: AdaptiveParams = FROZEN_PARAMS,
) -> dict[str, dict[str, EvalCounts]]:
    """Returns results[method][soil] (plus soil "all" pooled)."""
    seeds = tuple(seeds)
    results: dict[str, dict[str, EvalCounts]] = {m: {"all": EvalCounts()} for m in METHODS}
    for soil in soils:
        for m in METHODS:
            results[m][soil] = EvalCounts()
        for seed in seeds:
            per_method = run_methods(simulate_scenario(soil, seed), baseline, adaptive)
            for m, counts in per_method.items():
                results[m][soil].add(counts)
                results[m]["all"].add(counts)
    return results
