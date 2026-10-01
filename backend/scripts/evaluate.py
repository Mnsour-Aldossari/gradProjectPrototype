"""Write docs/EVALUATION_RESULTS.md from the evaluation report (evaluation seeds, frozen parameters).

Usage (from backend/):  .venv/Scripts/python -m scripts.evaluate

Uses the same report as GET /api/evaluation, so the document and the web page show the same numbers.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.evaluation.report import evaluation_report

OUT = Path(__file__).resolve().parents[2] / "docs" / "EVALUATION_RESULTS.md"
METHOD_LABELS = {"baseline": "Fixed threshold (baseline)", "adaptive": "Adaptive"}


def render(report: dict) -> str:
    p = report["protocol"]
    lines = [
        "# Evaluation Results — Baseline vs. Adaptive Detection",
        "",
        "> **النتائج على بيانات محاكاة.** " + report["notice"],
        "",
        f"Generated {date.today().isoformat()} by `backend/scripts/evaluate.py` from the frozen detectors. The web "
        "page (Evaluation) shows the same report. Protocol, seeds and calibration: "
        "[EVALUATION_PROTOCOL.md](EVALUATION_PROTOCOL.md).",
        "",
        f"- Evaluation seeds {p['evaluation_seeds'][0]}–{p['evaluation_seeds'][1]} × 3 soil types = "
        f"{p['scenarios']} simulated surveys (tuning seeds {p['tuning_seeds'][0]}–{p['tuning_seeds'][1]} were "
        "used for calibration only).",
        f"- Survey: sensor height {p['survey']['altitude_m']} m, speed {p['survey']['speed_mps']} m/s, "
        f"line spacing {p['survey']['line_spacing_m']} m; match radius {p['match_radius_m']} m.",
        f"- Reported detections: {p['reported_categories']}. Every output is a potential detection for "
        "verification by trained personnel.",
        "",
        "## Results by soil type",
        "",
        "| Soil | Method | Targets | Found | Missed | False alarms | Recall | Precision | F1 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for soil in report["soils"]:
        for method in ("baseline", "adaptive"):
            r = report["results"][method][soil["key"]]
            label = f"**{soil['label']}**" if soil["key"] == "all" else soil["label"]
            lines.append(
                f"| {label} | {METHOD_LABELS[method]} | {r['targets']} | {r['tp']} | {r['fn']} | {r['fp']} | "
                f"{r['recall']:.3f} | {r['precision']:.3f} | {r['f1']:.3f} |"
            )

    lines += ["", "False-alarm causes (all soils):", ""]
    for method in ("baseline", "adaptive"):
        causes = report["results"][method]["all"]["fp_by_cause"]
        text = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in sorted(causes.items(), key=lambda kv: -kv[1]))
        lines.append(f"- {METHOD_LABELS[method]}: {text}")

    lines += [
        "",
        "## Known limitations — حدود معروفة",
        "",
    ]
    for item in report["limitations"]:
        lines.append(f"- **{item['title']}.** {item['text']}")

    lines += [
        "",
        "Borderline case per seed (" + report["borderline_case"]["description"] + "):",
        "",
    ]
    for b in report["borderline_case"]["seeds"]:
        lines.append(f"- seed {b['seed']}: {b['detail']}")

    lines += ["", "## Mandatory tests", "", "| ID | Test | Value | Result |", "|---|---|---|---|"]
    for t in report["mandatory_tests"]:
        lines.append(f"| {t['id']} | {t['name']} | {t['value']} | {'Pass' if t['passed'] else 'Fail'} |")

    fp = report["frozen_parameters"]
    rel = ", ".join(f"{s} (md {r['md']}, gpr {r['gpr']})" for s, r in fp["adaptive"]["reliability"].items())
    lines += [
        "",
        "## Frozen parameters used",
        "",
        f"- Baseline: metal-detector threshold {fp['baseline']['md_threshold']}",
        f"- Adaptive: k_md {fp['adaptive']['k_md']}, k_gpr {fp['adaptive']['k_gpr']}, "
        f"body ratio {fp['adaptive']['body_ratio']}; reliabilities {rel}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    OUT.write_text(render(evaluation_report()), encoding="utf-8")
    print(f"written {OUT}")


if __name__ == "__main__":
    main()
