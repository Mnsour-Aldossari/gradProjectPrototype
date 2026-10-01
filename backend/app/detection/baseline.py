"""Baseline detector: one fixed rule on the metal detector only.

This is the conventional approach the adaptive classifier is compared
against. It ignores soil type, flight altitude, object depth and GPR.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .clustering import cluster_hits
from .types import Candidate, Category, Hit, Reading

METHOD = "baseline"


@dataclass(frozen=True)
class BaselineConfig:
    # Provisional value (about 8x the dry-sand metal-detector p95 background).
    # It will be fixed once on tuning seeds before the held-out evaluation and not changed afterwards.
    md_threshold: float = 0.30
    link_radius_m: float = 2.5
    min_hits: int = 2


def detect_baseline(readings: Sequence[Reading], config: BaselineConfig = BaselineConfig()) -> list[Candidate]:
    hits = [Hit(r, r.md) for r in readings if r.md >= config.md_threshold]
    candidates = []
    for cluster in cluster_hits(hits, config.link_radius_m):
        x, y = cluster.center
        peak_md = cluster.peak.reading.md
        n = len(cluster.hits)
        is_detection = n >= config.min_hits
        explanation = (
            f"Fixed rule: metal-detector reading >= {config.md_threshold:.2f} in {n} sample(s), "
            f"peak {peak_md:.2f}. "
            + (
                "Reported as a potential detection."
                if is_detection
                else f"Fewer than {config.min_hits} samples, treated as a noise spike."
            )
            + " Soil type, altitude, depth and GPR are not considered."
        )
        candidates.append(
            Candidate(
                x=x,
                y=y,
                category=Category.HIGH if is_detection else Category.CLUTTER,
                confidence=min(1.0, peak_md / (2 * config.md_threshold)),
                peak_md=peak_md,
                peak_gpr=max(h.reading.gpr_amp for h in cluster.hits),
                est_depth_m=None,
                n_hits=n,
                method=METHOD,
                explanation=explanation,
                features={"md_threshold": config.md_threshold},
            )
        )
    return candidates
