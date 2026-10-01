"""Calibrate baseline and adaptive parameters on the TUNING seeds only.

Usage (from backend/):  .venv/Scripts/python -m scripts.calibrate

Objective for both methods: F1 of reported detections (HIGH + SUSPECT for the
adaptive method, HIGH for the baseline) pooled over all tuning seeds and all
soil types. Ties are broken by higher recall, then by grid order.
The chosen values are written to docs/calibration_result.json and copied by
hand into app/detection/params.py and app/detection/baseline.py.
"""

from __future__ import annotations

import itertools
import json
import time
from dataclasses import replace
from pathlib import Path

from app.detection.adaptive import classify
from app.detection.baseline import BaselineConfig, detect_baseline
from app.detection.context import condition_profile
from app.detection.evaluation import EvalCounts, evaluate
from app.detection.params import FROZEN_PARAMS, AdaptiveParams, SoilReliability
from app.detection.threshold import robust_scores
from app.evaluation.harness import simulate_scenario
from app.evaluation.protocol import MATCH_RADIUS_M, SOIL_TYPES, TUNING_SEEDS

BASELINE_THRESHOLDS = [round(0.10 + 0.02 * i, 2) for i in range(36)]  # 0.10 .. 0.80
K_MD = [3.0, 4.0, 5.0, 6.0]
K_GPR = [3.0, 4.0, 5.0, 6.0]
BODY_RATIO = [0.03, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.4]
RELIABILITY = [0.5, 0.75, 1.0]

OUT = Path(__file__).resolve().parents[2] / "docs" / "calibration_result.json"


def _key(c: EvalCounts) -> tuple[float, float]:
    return (round(c.f1, 9), round(c.recall, 9))


def calibrate_baseline(runs) -> tuple[BaselineConfig, EvalCounts]:
    best = None
    for threshold in BASELINE_THRESHOLDS:
        cfg = BaselineConfig(md_threshold=threshold)
        total = EvalCounts()
        for run in runs:
            total.add(evaluate(detect_baseline(run.readings, cfg), run.truths, MATCH_RADIUS_M))
        if best is None or _key(total) > _key(best[1]):
            best = (cfg, total)
    return best


def calibrate_adaptive(runs) -> tuple[tuple[AdaptiveParams, EvalCounts], tuple[AdaptiveParams, EvalCounts]]:
    """Returns (best with per-soil reliabilities, best with one reliability shared by all soils)."""
    # Background scores depend only on design constants, so compute them once per run.
    cache = []
    for run in runs:
        profile = condition_profile(run.context, FROZEN_PARAMS)
        md = [r.md for r in run.readings]
        gpr = [r.gpr_amp for r in run.readings]
        md_res, md_z = robust_scores(md, profile.half_window, profile.guard)
        gpr_res, gpr_z = robust_scores(gpr, profile.half_window, profile.guard)
        cache.append((run, md_res, md_z, gpr_res, gpr_z))

    rel_grid = list(itertools.product(RELIABILITY, RELIABILITY))
    best = best_uniform = None
    for k_md, k_gpr, body in itertools.product(K_MD, K_GPR, BODY_RATIO):
        # counts[soil][(r_md, r_gpr)]
        counts: dict[str, dict[tuple[float, float], EvalCounts]] = {s: {} for s in SOIL_TYPES}
        for r_md, r_gpr in rel_grid:
            params = AdaptiveParams(
                k_md=k_md,
                k_gpr=k_gpr,
                body_ratio=body,
                reliability={s: SoilReliability(md=r_md, gpr=r_gpr) for s in SOIL_TYPES},
            )
            for run, md_res, md_z, gpr_res, gpr_z in cache:
                profile = condition_profile(run.context, params)
                cands = classify(run.readings, md_res, md_z, gpr_res, gpr_z, profile, params)
                counts[run.soil_type].setdefault((r_md, r_gpr), EvalCounts()).add(
                    evaluate(cands, run.truths, MATCH_RADIUS_M)
                )
        for choice in itertools.product(rel_grid, repeat=len(SOIL_TYPES)):
            total = EvalCounts()
            for soil, rel in zip(SOIL_TYPES, choice, strict=True):
                total.add(counts[soil][rel])
            params = AdaptiveParams(
                k_md=k_md,
                k_gpr=k_gpr,
                body_ratio=body,
                reliability={
                    s: SoilReliability(md=rel[0], gpr=rel[1]) for s, rel in zip(SOIL_TYPES, choice, strict=True)
                },
            )
            if best is None or _key(total) > _key(best[1]):
                best = (replace(params), total)
            # Ablation: the same reliability for every soil (no per-soil adaptation of weights).
            if len(set(choice)) == 1 and (best_uniform is None or _key(total) > _key(best_uniform[1])):
                best_uniform = (replace(params), total)
    return best, best_uniform


def main() -> None:
    started = time.time()
    runs = [simulate_scenario(soil, seed) for soil in SOIL_TYPES for seed in TUNING_SEEDS]
    print(f"simulated {len(runs)} tuning scenarios (seeds {TUNING_SEEDS[0]}-{TUNING_SEEDS[-1]})")

    baseline_cfg, baseline_counts = calibrate_baseline(runs)
    print(f"baseline: md_threshold={baseline_cfg.md_threshold}  tuning F1={baseline_counts.f1:.3f}")

    (params, adaptive_counts), (uniform, uniform_counts) = calibrate_adaptive(runs)
    for label, p, c in (("adaptive", params, adaptive_counts), ("ablation (shared reliability)", uniform, uniform_counts)):
        print(
            f"{label}: k_md={p.k_md} k_gpr={p.k_gpr} body_ratio={p.body_ratio} "
            f"reliability={ {s: (r.md, r.gpr) for s, r in p.reliability.items()} }  tuning F1={c.f1:.3f} "
            f"recall={c.recall:.3f} precision={c.precision:.3f}"
        )

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "data": "tuning seeds only",
                "tuning_seeds": [TUNING_SEEDS[0], TUNING_SEEDS[-1]],
                "soil_types": list(SOIL_TYPES),
                "objective": "pooled F1 of reported detections; ties -> higher recall -> grid order",
                "grids": {
                    "baseline_md_threshold": BASELINE_THRESHOLDS,
                    "k_md": K_MD,
                    "k_gpr": K_GPR,
                    "body_ratio": BODY_RATIO,
                    "reliability_md_and_gpr_per_soil": RELIABILITY,
                },
                "baseline": {"md_threshold": baseline_cfg.md_threshold, "tuning": baseline_counts.to_dict()},
                "adaptive": {
                    "k_md": params.k_md,
                    "k_gpr": params.k_gpr,
                    "body_ratio": params.body_ratio,
                    "reliability": {s: {"md": r.md, "gpr": r.gpr} for s, r in params.reliability.items()},
                    "tuning": adaptive_counts.to_dict(),
                },
                "ablation_shared_reliability": {
                    "note": "best result when every soil type must use the same reliabilities",
                    "k_md": uniform.k_md,
                    "k_gpr": uniform.k_gpr,
                    "body_ratio": uniform.body_ratio,
                    "reliability": next(iter(uniform.reliability.values())).__dict__,
                    "tuning": uniform_counts.to_dict(),
                },
            },
            indent=2,
        )
    )
    print(f"written {OUT} in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
