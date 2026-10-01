"""Adaptive detection and classification.

Instead of one fixed rule, the decision adapts to the survey conditions:

1. Condition profile - soil type, altitude and speed set sensor reliabilities,
   the background window and the clustering radius (context.py).
2. Adaptive threshold - each sensor is compared with its own local background
   (rolling median + k x MAD), so soil responses that vary across the area do
   not trigger detections (threshold.py).
3. Features per object - normalised metal and radar evidence, the GPR/MD body
   ratio, and depth estimated from radar travel time using the soil's permittivity.
4. Spatial clustering - all hits from one buried object become one candidate.
5. Reliability-weighted decision - the same sensor evidence is read differently
   in different soils (e.g. a missing radar reflection counts against a metal
   object only where radar penetrates well).

Every output is a potential detection for verification by trained personnel.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Sequence

from .clustering import Cluster, cluster_hits
from .context import ConditionProfile, SurveyContext, condition_profile
from .params import FROZEN_PARAMS, AdaptiveParams
from .threshold import RollingRobustScaler
from .types import Candidate, Category, Hit, Reading

METHOD = "adaptive"
SPEED_OF_LIGHT_M_PER_NS = 0.2998

CATEGORY_BASE_CONFIDENCE = {Category.HIGH: 0.65, Category.SUSPECT: 0.35, Category.CLUTTER: 0.05}


def _confidence(category: Category, evidence: float) -> float:
    """Ranking score within the category band; not a probability."""
    return CATEGORY_BASE_CONFIDENCE[category] + 0.3 * (1 - math.exp(-evidence / 4))


def _describe(
    reason: str, mu: float, rho: float, ratio: float, depth: float | None, p: ConditionProfile, params: AdaptiveParams
) -> str:
    sensors = f"Metal detector at {mu:.1f}x and radar at {rho:.1f}x their local adaptive thresholds"
    depth_text = f"; estimated depth {depth:.2f} m" if depth is not None else ""
    soil = (
        f"Soil: {p.soil_label} (metal-detector reliability {p.md_reliability:.2f}, "
        f"radar reliability {p.gpr_reliability:.2f})."
    )
    verdicts = {
        "spike": "Isolated single-sample response, treated as noise.",
        "deep": f"Reflector deeper than typical burial depth ({params.max_mine_depth_m:.2f} m): likely a natural structure.",
        "metal_with_body": (
            f"Metal response with a matching radar reflection (body ratio {ratio:.2f}): "
            "consistent with a buried object with metal content."
        ),
        "metal_without_body_trusted": (
            f"Metal response with little radar reflection (body ratio {ratio:.2f}) in a soil where radar "
            "penetrates well: consistent with small metal fragments."
        ),
        "metal_without_body_untrusted": (
            f"Metal response with little radar reflection (body ratio {ratio:.2f}), but radar is attenuated "
            "in this soil, so the object cannot be ruled out."
        ),
        "metal_weak_radar": "Metal response with a weak radar reflection.",
        "non_metallic_reflector": (
            "Radar reflector without a significant metal response: consistent with a low-metal or plastic "
            "object, or a stone."
        ),
    }
    return f"{soil} {sensors}{depth_text}. {verdicts[reason]}"


def classify_cluster(
    cluster: Cluster,
    readings: Sequence[Reading],
    md_res: Sequence[float],
    md_z: Sequence[float],
    gpr_res: Sequence[float],
    gpr_z: Sequence[float],
    profile: ConditionProfile,
    params: AdaptiveParams,
) -> Candidate:
    k_md = params.k_md / profile.md_reliability
    k_gpr = params.k_gpr
    idx = [h.index for h in cluster.hits]

    mu = max(md_z[i] for i in idx) / k_md
    rho = max(gpr_z[i] for i in idx) / k_gpr
    md_peak = max(md_res[i] for i in idx)
    gpr_peak = max(gpr_res[i] for i in idx)
    ratio = gpr_peak / md_peak if md_peak > 0 else math.inf

    radar_idx = [i for i in idx if gpr_z[i] >= k_gpr]
    depth = None
    if radar_idx:
        twt = statistics.median(readings[i].gpr_twt_ns for i in radar_idx)
        depth = max(0.0, twt * SPEED_OF_LIGHT_M_PER_NS / (2 * math.sqrt(profile.permittivity)))

    md_detected = mu >= 1
    gpr_detected = rho >= 1
    has_body = ratio >= params.body_ratio * profile.gpr_reliability

    if len(idx) < params.min_hits:
        category, reason = Category.CLUTTER, "spike"
    elif depth is not None and depth > params.max_mine_depth_m:
        category, reason = Category.CLUTTER, "deep"
    elif md_detected and gpr_detected and has_body:
        category, reason = Category.HIGH, "metal_with_body"
    elif md_detected and not has_body:
        if profile.radar_trusted:
            category, reason = Category.CLUTTER, "metal_without_body_trusted"
        else:
            category, reason = Category.SUSPECT, "metal_without_body_untrusted"
    elif md_detected:
        category, reason = Category.SUSPECT, "metal_weak_radar"
    else:
        category, reason = Category.SUSPECT, "non_metallic_reflector"

    cap = params.evidence_cap
    evidence = profile.md_reliability * min(mu, cap) + profile.gpr_reliability * min(rho, cap)
    x, y = cluster.center
    return Candidate(
        x=x,
        y=y,
        category=category,
        confidence=round(_confidence(category, evidence), 3),
        peak_md=max(readings[i].md for i in idx),
        peak_gpr=max(readings[i].gpr_amp for i in idx),
        est_depth_m=depth,
        n_hits=len(idx),
        method=METHOD,
        explanation=_describe(reason, mu, rho, ratio, depth, profile, params),
        features={
            "reason": reason,
            "md_evidence": round(mu, 3),
            "gpr_evidence": round(rho, 3),
            "body_ratio": round(ratio, 3) if math.isfinite(ratio) else None,
            "body_ratio_min": round(params.body_ratio * profile.gpr_reliability, 3),
            "md_threshold_k": round(k_md, 3),
            "gpr_threshold_k": round(k_gpr, 3),
            "md_reliability": profile.md_reliability,
            "gpr_reliability": profile.gpr_reliability,
            "soil_type": profile.soil_type,
            "evidence": round(evidence, 3),
        },
    )


def classify(
    readings: Sequence[Reading],
    md_res: Sequence[float],
    md_z: Sequence[float],
    gpr_res: Sequence[float],
    gpr_z: Sequence[float],
    profile: ConditionProfile,
    params: AdaptiveParams,
) -> list[Candidate]:
    k_md = params.k_md / profile.md_reliability
    k_gpr = params.k_gpr
    hits = []
    for i, r in enumerate(readings):
        score = max(md_z[i] / k_md, gpr_z[i] / k_gpr)
        if score >= 1:
            hits.append(Hit(r, score, i))
    return [
        classify_cluster(c, readings, md_res, md_z, gpr_res, gpr_z, profile, params)
        for c in cluster_hits(hits, profile.link_radius_m)
    ]


class AdaptiveDetector:
    """Streaming adaptive detector: add readings as they arrive, ask for candidates any time."""

    def __init__(self, context: SurveyContext, params: AdaptiveParams = FROZEN_PARAMS) -> None:
        self.params = params
        self.profile = condition_profile(context, params)
        self._readings: list[Reading] = []
        self._md = RollingRobustScaler(self.profile.half_window, self.profile.guard)
        self._gpr = RollingRobustScaler(self.profile.half_window, self.profile.guard)

    def add(self, readings: Iterable[Reading]) -> None:
        new = list(readings)
        self._readings.extend(new)
        self._md.extend(r.md for r in new)
        self._gpr.extend(r.gpr_amp for r in new)

    def candidates(self) -> list[Candidate]:
        md_res, md_z = self._md.scores()
        gpr_res, gpr_z = self._gpr.scores()
        return classify(self._readings, md_res, md_z, gpr_res, gpr_z, self.profile, self.params)


def detect_adaptive(
    readings: Sequence[Reading], context: SurveyContext, params: AdaptiveParams = FROZEN_PARAMS
) -> list[Candidate]:
    detector = AdaptiveDetector(context, params)
    detector.add(readings)
    return detector.candidates()
