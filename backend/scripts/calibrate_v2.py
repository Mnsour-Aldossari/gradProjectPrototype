"""Calibrate the version 2 adaptive detector (app/detection/adaptive_v2.py) on the TUNING seeds only.

Usage (from backend/):  .venv/Scripts/python -m scripts.calibrate_v2

Data: the tuning seeds x the three soils, each flown at the five tuning settings below, so the thresholds hold at
other heights, speeds and lane spacings than the standard one. Objective: the most mines found (recall of high +
needs verification, pooled over all of them) with no more false alarms than version 1 on the same surveys; ties go
to fewer false alarms, then to grid order. (A first objective, F1 as version 1's, traded mines found for fewer false
alarms: at the standard setting it found fewer mines than version 1. Missing a mine costs more than a false alarm,
so the objective was changed, on tuning data, before any evaluation.) The soil reliabilities stay version 1's
(app/detection/params.py). Writes docs/calibration_result_v2.json (version 1's
docs/calibration_result.json is left as it is); the chosen values are copied by hand into
app/detection/params_v2.py. The evaluation seeds are not used.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from itertools import product
from pathlib import Path

from app.detection.adaptive import detect_adaptive
from app.detection.adaptive_v2 import AdaptiveDetectorV2, AdaptiveV2Params, classify_v2
from app.detection.evaluation import EvalCounts, evaluate
from app.detection.params import FROZEN_PARAMS
from app.evaluation.harness import simulate_scenario
from app.evaluation.protocol import MATCH_RADIUS_M, SOIL_TYPES, STANDARD_SURVEY, TUNING_SEEDS

# (height m, speed m/s, lane spacing m): the standard survey first.
TUNING_SETTINGS = ((1.5, 2.0, 2.0), (1.0, 1.0, 1.0), (0.75, 2.0, 2.0), (1.5, 1.0, 1.0), (2.0, 2.0, 2.0))
# The first run had k_md 3.0..10.0, k_gpr 4.0..12.0 and max_reflector_depth_m 0.12..0.3. With the F1 objective the
# best sat on the lower edges of k_md and the depth, and with the final objective on the lower edge of k_gpr, so those
# grids were extended downward and the calibration run again, still on tuning seeds only.
K_MD = (2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0)
K_GPR = (3.0, 3.5, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0)
BODY_RATIO = (0.05, 0.075, 0.1, 0.15, 0.2)
MAX_REFLECTOR_DEPTH_M = (0.06, 0.08, 0.1, 0.12, 0.15, 0.2, 0.3)
SMOOTH = (False, True)
RELIABILITY = dict(FROZEN_PARAMS.reliability)

OUT = Path(__file__).resolve().parents[2] / "docs" / "calibration_result_v2.json"


def grid() -> list[AdaptiveV2Params]:
    return [
        AdaptiveV2Params(k_md, k_gpr, ratio, depth, smooth, RELIABILITY)
        for smooth, k_md, k_gpr, ratio, depth in product(SMOOTH, K_MD, K_GPR, BODY_RATIO, MAX_REFLECTOR_DEPTH_M)
    ]


def score_run(job: tuple[str, int, tuple[float, float, float]]) -> list[tuple[int, int, int]]:
    """(targets, found, false alarms) of one tuning survey for version 1, then every grid point in grid order."""
    soil, seed, (altitude, speed, spacing) = job
    survey = {**STANDARD_SURVEY, "altitude_m": altitude, "speed_mps": speed, "line_spacing_m": spacing}
    run = simulate_scenario(soil, seed, survey)
    scores = {}
    for smooth in SMOOTH:  # the background scores depend only on the matched filter, not on the thresholds
        d = AdaptiveDetectorV2(run.context, AdaptiveV2Params(4.0, 5.0, 0.1, 0.3, smooth, RELIABILITY))
        d.add(run.readings)
        scores[smooth] = (d.profile, d.scores())
    v1 = evaluate(detect_adaptive(run.readings, run.context), run.truths, MATCH_RADIUS_M)
    out = [(v1.targets, v1.tp, v1.fp)]
    for p in grid():
        profile, s = scores[p.smooth]
        c = evaluate(classify_v2(run.readings, *s, profile, p), run.truths, MATCH_RADIUS_M)
        out.append((c.targets, c.tp, c.fp))
    return out


def main() -> None:
    started = time.monotonic()
    jobs = list(product(SOIL_TYPES, TUNING_SEEDS, TUNING_SETTINGS))
    params = grid()
    v1 = EvalCounts()
    totals = [EvalCounts() for _ in params]
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 2)) as pool:
        for result in pool.map(score_run, jobs, chunksize=1):
            for total, (targets, tp, fp) in zip([v1, *totals], result, strict=True):
                total.targets += targets
                total.tp += tp
                total.fp += fp
    feasible = [i for i in range(len(params)) if totals[i].fp <= v1.fp]
    order = sorted(feasible, key=lambda i: (-totals[i].tp, totals[i].fp, i))
    best = order[0]

    def entry(i: int) -> dict:
        p, c = params[i], totals[i]
        return {
            "k_md": p.k_md, "k_gpr": p.k_gpr, "body_ratio": p.body_ratio,
            "max_reflector_depth_m": p.max_reflector_depth_m, "smooth": p.smooth,
            "f1": round(c.f1, 4), "recall": round(c.recall, 4), "precision": round(c.precision, 4),
            "targets": c.targets, "found": c.tp, "false_alarms": c.fp,
        }  # fmt: skip

    result = {
        "method": "adaptive v2",
        "data": {
            "tuning_seeds": [TUNING_SEEDS[0], TUNING_SEEDS[-1]],
            "soils": list(SOIL_TYPES),
            "settings": [{"altitude_m": a, "speed_mps": s, "line_spacing_m": d} for a, s, d in TUNING_SETTINGS],
            "surveys": len(jobs),
        },
        "objective": "most mines found (high + needs verification, pooled) with false alarms <= version 1's; "
        "ties: fewer false alarms, then grid order",
        "v1_on_the_same_surveys": {"targets": v1.targets, "found": v1.tp, "false_alarms": v1.fp,
                                   "recall": round(v1.recall, 4), "precision": round(v1.precision, 4)},  # fmt: skip
        "grid": {
            "k_md": list(K_MD), "k_gpr": list(K_GPR), "body_ratio": list(BODY_RATIO),
            "max_reflector_depth_m": list(MAX_REFLECTOR_DEPTH_M), "smooth": list(SMOOTH),
        },  # fmt: skip
        "reliability": "version 1's, unchanged",
        "best": entry(best),
        "best_without_smoothing": entry(next(i for i in order if not params[i].smooth)),
        "best_with_smoothing": entry(next((i for i in order if params[i].smooth), order[0])),
        "best_by_f1": entry(max(range(len(params)), key=lambda i: (round(totals[i].f1, 9), -i))),
        "top10": [entry(i) for i in order[:10]],
        "seconds": round(time.monotonic() - started),
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["best"]), json.dumps(result["best_without_smoothing"]), f"{result['seconds']} s", sep="\n")


if __name__ == "__main__":
    main()
