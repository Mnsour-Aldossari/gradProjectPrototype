"""Evaluate the version 2 adaptive detector once, as docs/EVALUATION_PROTOCOL_V2.md says, against version 1 and the
fixed-threshold baseline, all frozen.

Usage (from backend/):  .venv/Scripts/python -m scripts.evaluate_v2

Primary data: the fresh evaluation seeds 4000-4029 (never used before) x the three soils x the five settings of the
protocol. Secondary: version 1's evaluation seeds 2000-2029 at the standard setting, for continuity with
docs/EVALUATION_RESULTS.md. Writes docs/EVALUATION_RESULTS_V2.md and docs/evaluation_v2.json and applies the
protocol's adoption rule. Version 1's results files are left as they are. Simulated data.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from itertools import product
from pathlib import Path

from app.detection import BaselineConfig, detect_baseline
from app.detection.adaptive import detect_adaptive
from app.detection.adaptive_v2 import detect_adaptive_v2
from app.detection.evaluation import EvalCounts, evaluate
from app.detection.params_v2 import FROZEN_PARAMS_V2
from app.evaluation.harness import simulate_scenario
from app.evaluation.protocol import EVALUATION_SEEDS, MATCH_RADIUS_M, SOIL_TYPES, STANDARD_SURVEY
from app.evaluation.protocol_v2 import ADOPTION, EVALUATION_SETTINGS, EVALUATION_SEEDS_V2

DOCS = Path(__file__).resolve().parents[2] / "docs"
METHODS = ("baseline", "v1", "v2")
LABELS = {"baseline": "Fixed threshold (baseline)", "v1": "Adaptive v1", "v2": "Adaptive v2"}
SOIL_LABELS = {"dry_sand": "Dry sand", "wet_clay": "Wet clay", "mineralized_rocky": "Mineralised rocky soil"}


def run(job: tuple[str, int, tuple[float, float, float]]) -> tuple[tuple, str, dict[str, EvalCounts]]:
    soil, seed, (altitude, speed, spacing) = job
    r = simulate_scenario(soil, seed, {**STANDARD_SURVEY, "altitude_m": altitude, "speed_mps": speed,
                                       "line_spacing_m": spacing})  # fmt: skip
    found = {
        "baseline": detect_baseline(r.readings, BaselineConfig()),
        "v1": detect_adaptive(r.readings, r.context),
        "v2": detect_adaptive_v2(r.readings, r.context, FROZEN_PARAMS_V2),
    }
    return (altitude, speed, spacing), soil, {m: evaluate(c, r.truths, MATCH_RADIUS_M) for m, c in found.items()}


def tally(jobs: list) -> dict:
    """{setting: {soil or "all": {method: EvalCounts}}}"""
    out: dict = {}
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 2)) as pool:
        for setting, soil, counts in pool.map(run, jobs, chunksize=1):
            for key in (soil, "all"):
                cell = out.setdefault(setting, {}).setdefault(key, {m: EvalCounts() for m in METHODS})
                for m in METHODS:
                    cell[m].add(counts[m])
    return out


def pooled(results: dict, method: str) -> EvalCounts:
    total = EvalCounts()
    for setting in results:
        total.add(results[setting]["all"][method])
    return total


def counts_json(c: EvalCounts) -> dict:
    low = c.outcomes.get("low_metal_mine", {})
    return {
        "targets": c.targets, "found": c.tp, "false_alarms": c.fp, "recall": round(c.recall, 4),
        "precision": round(c.precision, 4), "f1": round(c.f1, 4), "low_metal": sum(low.values()),
        "low_metal_found": low.get("reported", 0), "false_alarm_causes": dict(c.fp_by_cause),
    }  # fmt: skip


def adoption(fresh: dict) -> tuple[bool, list[tuple[str, str, bool]]]:
    standard = EVALUATION_SETTINGS[0]
    v1s, v2s = fresh[standard]["all"]["v1"], fresh[standard]["all"]["v2"]
    v1a, v2a = pooled(fresh, "v1"), pooled(fresh, "v2")
    checks = [
        (f"Recall over the five settings at least {ADOPTION['recall_gain_all']:.2f} above v1's",
         f"{v2a.recall:.3f} vs {v1a.recall:.3f}", v2a.recall >= v1a.recall + ADOPTION["recall_gain_all"]),
        ("False alarms over the five settings not more than v1's", f"{v2a.fp} vs {v1a.fp}", v2a.fp <= v1a.fp),
        (f"Recall at the standard setting not more than {ADOPTION['recall_loss_standard']:.2f} below v1's",
         f"{v2s.recall:.3f} vs {v1s.recall:.3f}", v2s.recall >= v1s.recall - ADOPTION["recall_loss_standard"]),
    ]  # fmt: skip
    return all(ok for *_, ok in checks), checks


def report(fresh: dict, old: dict, adopted: bool, checks: list, seconds: float) -> str:
    def row(label: str, m: str, c: EvalCounts) -> str:
        low = c.outcomes.get("low_metal_mine", {})
        return (f"| {label} | {LABELS[m]} | {c.targets} | {c.tp} | {c.fp} | {c.recall:.3f} | {c.precision:.3f} | "
                f"{c.f1:.3f} | {low.get('reported', 0)}/{sum(low.values())} |")  # fmt: skip

    head = "| Soil | Method | Targets | Found | False alarms | Recall | Precision | F1 | Low-metal found |\n"
    head += "|---" * 9 + "|"
    lines = [
        "# Evaluation Results — Adaptive v2 vs. v1 vs. Baseline",
        "",
        "> **النتائج على بيانات محاكاة.** Results on simulated data. The simulator is not calibrated against real "
        "sensors; the numbers compare the methods inside the simulation and do not predict field performance.",
        "",
        f"Generated {date.today().isoformat()} by `backend/scripts/evaluate_v2.py`, once, from the frozen "
        "detectors, as [EVALUATION_PROTOCOL_V2.md](EVALUATION_PROTOCOL_V2.md) says. Version 1's results "
        "([EVALUATION_RESULTS.md](EVALUATION_RESULTS.md)) are unchanged.",
        "",
        f"- Fresh evaluation seeds {EVALUATION_SEEDS_V2[0]}–{EVALUATION_SEEDS_V2[-1]} × 3 soils × "
        f"{len(EVALUATION_SETTINGS)} settings = {len(EVALUATION_SEEDS_V2) * 3 * len(EVALUATION_SETTINGS)} simulated "
        f"surveys; match radius {MATCH_RADIUS_M} m; reported: high + needs verification (baseline: high).",
        "",
        "## Adoption rule",
        "",
        "| Condition | v2 vs v1 | Met |",
        "|---|---|---|",
        *[f"| {name} | {value} | {'Yes' if ok else 'No'} |" for name, value, ok in checks],
        "",
        f"**Decision: {'v2 replaces v1 in the app.' if adopted else 'v1 stays in the app.'}**",
        "",
    ]
    for setting in EVALUATION_SETTINGS:
        a, s, d = setting
        tag = " (standard)" if setting == EVALUATION_SETTINGS[0] else ""
        lines += [f"## Height {a} m, speed {s} m/s, lanes {d} m{tag}", "", head]
        for soil in (*SOIL_TYPES, "all"):
            label = "**All soils**" if soil == "all" else SOIL_LABELS[soil]
            lines += [row(label, m, fresh[setting][soil][m]) for m in METHODS]
        lines.append("")
    lines += ["## All five settings pooled", "", head]
    lines += [row("**All**", m, pooled(fresh, m)) for m in METHODS]
    lines += [
        "",
        f"## Secondary: version 1's evaluation seeds {EVALUATION_SEEDS[0]}–{EVALUATION_SEEDS[-1]}, standard setting",
        "",
        "Version 2 was designed knowing version 1's limitations on these seeds, so this table is for continuity only.",
        "",
        head,
    ]
    std = EVALUATION_SETTINGS[0]
    for soil in (*SOIL_TYPES, "all"):
        label = "**All soils**" if soil == "all" else SOIL_LABELS[soil]
        lines += [row(label, m, old[std][soil][m]) for m in METHODS]
    lines += ["", f"Run time: {seconds:.0f} s.", ""]
    return "\n".join(lines)


def main() -> None:
    started = time.monotonic()
    fresh = tally(list(product(SOIL_TYPES, EVALUATION_SEEDS_V2, EVALUATION_SETTINGS)))
    old = tally(list(product(SOIL_TYPES, EVALUATION_SEEDS, EVALUATION_SETTINGS[:1])))
    adopted, checks = adoption(fresh)
    seconds = time.monotonic() - started
    (DOCS / "EVALUATION_RESULTS_V2.md").write_text(report(fresh, old, adopted, checks, seconds), encoding="utf-8")
    data = {
        "generated": date.today().isoformat(),
        "adopted": adopted,
        "checks": [{"condition": n, "value": v, "met": ok} for n, v, ok in checks],
        "fresh": {f"{a}/{s}/{d}": {soil: {m: counts_json(c) for m, c in cell.items()} for soil, cell in by.items()}
                  for (a, s, d), by in fresh.items()},  # fmt: skip
        "pooled": {m: counts_json(pooled(fresh, m)) for m in METHODS},
        "old_seeds_standard": {soil: {m: counts_json(c) for m, c in cell.items()}
                               for soil, cell in old[EVALUATION_SETTINGS[0]].items()},  # fmt: skip
    }
    (DOCS / "evaluation_v2.json").write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(f"{'ADOPTED' if adopted else 'NOT ADOPTED'}; {seconds:.0f} s")
    for name, value, ok in checks:
        print(f"  {'yes' if ok else 'no '} {name}: {value}")


if __name__ == "__main__":
    main()
