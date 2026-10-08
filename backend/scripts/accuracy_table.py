"""Builds the accuracy table behind the estimate shown while planning a mission (app/detection/accuracy.py).

For every soil and every combination of sensor height, speed and lane spacing on a grid, it flies the standard test
field on the estimate seeds (app/evaluation/protocol.py: neither tuning nor evaluation seeds) and scores the app's
live detector (detect_live: version 2) against the simulated ground truth, as the evaluation does. It writes app/detection/accuracy_table.json; it
does not touch docs/ or the frozen parameters. Simulated data: the table compares settings inside the simulation.

    .venv/Scripts/python -m scripts.accuracy_table            # a few minutes on several cores
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from itertools import product
from pathlib import Path

from app.detection.accuracy import ALTITUDES_M, SPACINGS_M, SPEEDS_MPS, TABLE_PATH
from app.detection import detect_live
from app.detection.evaluation import evaluate
from app.evaluation.harness import simulate_scenario
from app.evaluation.protocol import ESTIMATE_SEEDS, MATCH_RADIUS_M, SOIL_TYPES, STANDARD_SURVEY
from app.simulation.geo import LocalFrame, polygon_area

AREA_M2 = polygon_area([LocalFrame.centred_on(STANDARD_SURVEY["area"]).to_xy(*p) for p in STANDARD_SURVEY["area"]])


def run_cell(cell: tuple[str, float, float, float]) -> dict:
    soil, altitude, speed, spacing = cell
    survey = {**STANDARD_SURVEY, "altitude_m": altitude, "speed_mps": speed, "line_spacing_m": spacing}
    totals = {"surveys": 0, "targets": 0, "found": 0, "false_alarms": 0, "low_metal": 0, "low_metal_found": 0}
    for seed in ESTIMATE_SEEDS:
        run = simulate_scenario(soil, seed, survey)
        counts = evaluate(detect_live(run.readings, run.context), run.truths, MATCH_RADIUS_M)
        low = counts.outcomes.get("low_metal_mine", {})
        totals["surveys"] += 1
        totals["targets"] += counts.targets
        totals["found"] += counts.tp
        totals["false_alarms"] += counts.fp
        totals["low_metal"] += sum(low.values())
        totals["low_metal_found"] += low.get("reported", 0)
    return {"soil": soil, "altitude_m": altitude, "speed_mps": speed, "line_spacing_m": spacing, **totals}


def main() -> None:
    cells = list(product(SOIL_TYPES, ALTITUDES_M, SPEEDS_MPS, SPACINGS_M))
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 2)) as pool:
        rows = list(pool.map(run_cell, cells, chunksize=1))
    table = {
        "generated": date.today().isoformat(),
        "method": "adaptive v2",
        "seeds": [ESTIMATE_SEEDS[0], ESTIMATE_SEEDS[-1]],
        "survey_area_m2": round(AREA_M2, 1),
        "match_radius_m": MATCH_RADIUS_M,
        "altitudes_m": list(ALTITUDES_M),
        "speeds_mps": list(SPEEDS_MPS),
        "spacings_m": list(SPACINGS_M),
        "rows": rows,
    }
    TABLE_PATH.write_text(json.dumps(table, indent=1) + "\n", encoding="utf-8")
    print(f"{len(rows)} settings x {len(ESTIMATE_SEEDS)} surveys in {time.monotonic() - started:.0f} s -> {TABLE_PATH}")


if __name__ == "__main__":
    main()
