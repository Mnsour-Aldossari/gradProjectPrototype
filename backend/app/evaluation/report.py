"""Evaluation report on the evaluation seeds, shared by the API and docs/EVALUATION_RESULTS.md.

Computed from the frozen detectors every time the process starts (cached afterwards),
so the page and the document always show what the current code produces.
"""

from __future__ import annotations

import math
from functools import lru_cache

from app.detection import FROZEN_PARAMS, BaselineConfig, Category, detect_adaptive, detect_baseline
from app.detection.context import SOIL_LABELS
from app.detection.evaluation import EvalCounts, evaluate

from .harness import BORDERLINE_SEEDS, LOW_METAL_MINE_7CM, simulate_scenario, single_object_candidates
from .protocol import EVALUATION_SEEDS, MATCH_RADIUS_M, SOIL_TYPES, STANDARD_SURVEY, TUNING_SEEDS

NOTICE = (
    "Results on simulated data. The simulator is not calibrated against real sensors; the numbers compare "
    "the two methods inside the simulation and do not predict field performance."
)
METHODS = ("baseline", "adaptive")


def _missed(counts: EvalCounts, kind: str) -> tuple[int, int]:
    outcome = counts.outcomes.get(kind, {})
    total = sum(outcome.values())
    return total - outcome.get("reported", 0), total


def _pct(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


@lru_cache(maxsize=1)
def evaluation_report() -> dict:
    results = {m: {s: EvalCounts() for s in (*SOIL_TYPES, "all")} for m in METHODS}
    low_metal_total = low_metal_reported = 0
    low_metal_not_radar = 0
    scrap_with_candidate = scrap_clutter_only = 0

    for soil in SOIL_TYPES:
        for seed in EVALUATION_SEEDS:
            run = simulate_scenario(soil, seed)
            candidates = {
                "baseline": detect_baseline(run.readings),
                "adaptive": detect_adaptive(run.readings, run.context),
            }
            for method, cands in candidates.items():
                counts = evaluate(cands, run.truths, MATCH_RADIUS_M)
                results[method][soil].add(counts)
                results[method]["all"].add(counts)

            for obj in run.truths:
                near = [
                    c for c in candidates["adaptive"] if math.hypot(c.x - obj.x, c.y - obj.y) <= MATCH_RADIUS_M
                ]
                reported = [c for c in near if c.category != Category.CLUTTER]
                if obj.kind == "low_metal_mine":
                    low_metal_total += 1
                    if reported:
                        low_metal_reported += 1
                        low_metal_not_radar += sum(
                            not (c.features["gpr_evidence"] >= 1 and c.features["md_evidence"] < 1) for c in reported
                        )
                if obj.kind == "scrap_metal" and near:
                    scrap_with_candidate += 1
                    scrap_clutter_only += not reported

    borderline = []
    for seed in BORDERLINE_SEEDS:
        near = single_object_candidates(LOW_METAL_MINE_7CM, "dry_sand", seed)
        reported = [c for c in near if c.category != Category.CLUTTER]
        if reported:
            detail = f"reported ({reported[0].category.value}), radar at {reported[0].features['gpr_evidence']:.2f}x threshold"
        elif near:
            detail = f"only a {near[0].n_hits}-sample response at {near[0].features['gpr_evidence']:.2f}x radar threshold, treated as noise"
        else:
            detail = "no candidate"
        borderline.append({"seed": seed, "reported": bool(reported), "detail": detail})

    base_all, adapt_all = results["baseline"]["all"], results["adaptive"]["all"]
    base_dry, adapt_dry = results["baseline"]["dry_sand"], results["adaptive"]["dry_sand"]
    lm_missed, lm_total = _missed(adapt_all, "low_metal_mine")
    mm_missed_adaptive, mm_total = _missed(adapt_all, "metal_mine")
    mm_missed_baseline, _ = _missed(base_all, "metal_mine")
    borderline_found = sum(b["reported"] for b in borderline)

    limitations = [
        {
            "title": "No improvement in dry sand",
            "text": (
                f"In dry sand the adaptive method raised {adapt_dry.fp} false alarms against the baseline's {base_dry.fp}. "
                f"It removes scrap-metal alarms but reports buried rocks as radar-only reflectors instead "
                f"({adapt_dry.fp_by_cause.get('rock', 0)} of its dry-sand false alarms are rocks)."
            ),
        },
        {
            "title": "Many low-metal mines are not found",
            "text": (
                f"{lm_missed} of {lm_total} low-metal mines ({_pct(lm_missed, lm_total)} %) were not reported by the "
                "adaptive method. The baseline, which uses only the metal detector, reported none of them."
            ),
        },
        {
            "title": "More metal mines missed than the baseline",
            "text": (
                f"The adaptive method missed {mm_missed_adaptive} of {mm_total} metal mines; the baseline missed "
                f"{mm_missed_baseline}."
            ),
        },
        {
            "title": "Borderline case: low-metal mine 7 cm deep in dry sand",
            "text": (
                f"Its radar signal sits right at the frozen threshold. It was reported in {borderline_found} of "
                f"{len(borderline)} fixed seeds. This is kept as a known limitation; parameters were not re-tuned."
            ),
        },
    ]

    mandatory = [
        {
            "id": "T1",
            "name": "Adaptive raises fewer false alarms than the baseline",
            "value": f"{adapt_all.fp} vs {base_all.fp}",
            "passed": adapt_all.fp < base_all.fp,
        },
        {
            "id": "T2",
            "name": "More than half of the low-metal mines are found, all through radar",
            "value": f"{low_metal_reported} / {low_metal_total} ({_pct(low_metal_reported, low_metal_total)} %), "
            f"{low_metal_not_radar} not radar-driven",
            "passed": low_metal_reported / low_metal_total > 0.5 and low_metal_not_radar == 0,
        },
        {
            "id": "T3",
            "name": "More than half of the scrap objects are classified as likely clutter",
            "value": f"{scrap_clutter_only} / {scrap_with_candidate} ({_pct(scrap_clutter_only, scrap_with_candidate)} %)",
            "passed": scrap_clutter_only / scrap_with_candidate > 0.5,
        },
    ]

    return {
        "simulated": True,
        "notice": NOTICE,
        "protocol": {
            "evaluation_seeds": [EVALUATION_SEEDS[0], EVALUATION_SEEDS[-1]],
            "tuning_seeds": [TUNING_SEEDS[0], TUNING_SEEDS[-1]],
            "scenarios": len(EVALUATION_SEEDS) * len(SOIL_TYPES),
            "survey": {k: v for k, v in STANDARD_SURVEY.items() if k != "area"},
            "match_radius_m": MATCH_RADIUS_M,
            "reported_categories": "adaptive: high + suspect; baseline: high",
        },
        "frozen_parameters": {
            "baseline": {"md_threshold": BaselineConfig().md_threshold},
            "adaptive": {
                "k_md": FROZEN_PARAMS.k_md,
                "k_gpr": FROZEN_PARAMS.k_gpr,
                "body_ratio": FROZEN_PARAMS.body_ratio,
                "reliability": {s: {"md": r.md, "gpr": r.gpr} for s, r in FROZEN_PARAMS.reliability.items()},
            },
        },
        "soils": [{"key": s, "label": SOIL_LABELS[s]} for s in SOIL_TYPES] + [{"key": "all", "label": "All soils"}],
        "results": {m: {s: c.to_dict() for s, c in by_soil.items()} for m, by_soil in results.items()},
        "mandatory_tests": mandatory,
        "borderline_case": {
            "description": "Lone low-metal mine, 7 cm deep, 11 cm wide, in dry sand (adaptive method)",
            "seeds": borderline,
        },
        "limitations": limitations,
    }
