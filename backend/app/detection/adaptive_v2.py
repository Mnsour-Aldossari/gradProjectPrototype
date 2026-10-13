"""Adaptive detection, version 2: the version 1 method (adaptive.py, frozen and unchanged) with three changes.

1. Height-corrected body ratio. Version 1 compares the radar's response with the metal detector's (the body
   ratio) against one minimum, calibrated at 1.5 m. Flying lower, the metal detector's response grows much faster
   than the radar's (about (height + depth)^-3 against (1 + 0.4 height)^-2), so below 1.5 m the ratio of a metal
   mine falls under the minimum and it was taken for scrap. Version 2 divides each sensor's response by its gain at
   the reading's height relative to the reference height, so the ratio means the same at any height.
2. Matched filter along the track. Before the local background, each sensor's readings are averaged with their
   neighbours within the sensor's footprint (Gaussian weights by ground distance, so readings across a turn do not
   mix). A weak response spread over several readings, as from a low-metal mine, then stands out of the noise.
3. Shallower limit for reflectors without metal. A radar reflector with no metal response deeper than
   max_reflector_depth_m is taken for a stone or a natural structure (anti-personnel mines lie shallow); metal
   objects keep version 1's limit.

The sensors' height response and footprint are a sensor characterisation: in the field they are measured once per
sensor over a test target; here they are the simulated sensors' (app/simulation/sensors.py). Parameters marked
"calibrated" are chosen on the tuning seeds only (scripts/calibrate_v2.py, docs/EVALUATION_PROTOCOL_V2.md).
Every output is a potential detection for verification by trained personnel.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .adaptive import SPEED_OF_LIGHT_M_PER_NS, _confidence
from .clustering import Cluster, cluster_hits
from .context import ConditionProfile, SurveyContext, condition_profile
from .params import AdaptiveParams, SoilReliability
from .threshold import robust_scores
from .types import Candidate, Category, Hit, Reading

METHOD = "adaptive"
VERSION = 2

# Sensor characterisation (see the module docstring).
MD_REFERENCE_DEPTH_M = 0.1  # typical burial depth in the metal detector's stand-off
GPR_SPREADING = 0.4  # radar spreading loss: (1 + 0.4 height)^-2
TYPICAL_OBJECT_SIZE_M = 0.12


@dataclass(frozen=True)
class AdaptiveV2Params:
    k_md: float  # calibrated
    k_gpr: float  # calibrated
    body_ratio: float  # calibrated; minimum height-corrected GPR/MD ratio at the reference height
    max_reflector_depth_m: float  # calibrated; deeper reflectors without metal are natural structures
    smooth: bool  # calibrated; matched filter along the track
    reliability: dict[str, SoilReliability]
    reference_height_m: float = 1.5  # where body_ratio holds as it is (version 1 was calibrated there)

    def as_v1(self) -> AdaptiveParams:
        """Version 1's parameters with these thresholds: the design constants, profile and clustering it shares."""
        return AdaptiveParams(
            k_md=self.k_md, k_gpr=self.k_gpr, body_ratio=self.body_ratio, reliability=self.reliability
        )


def md_gain(height_m: float) -> float:
    return 1 / (max(height_m, 0.0) + MD_REFERENCE_DEPTH_M) ** 3


def gpr_gain(height_m: float) -> float:
    return 1 / (1 + GPR_SPREADING * max(height_m, 0.0)) ** 2


def footprint_m(height_m: float) -> float:
    """The radar's footprint (one standard deviation, metres) over a typical object; the metal detector's is close."""
    return 0.25 + 0.2 * max(height_m, 0.0) + TYPICAL_OBJECT_SIZE_M / 2


def smoothed(readings: Sequence[Reading], values: Sequence[float], start: int, stop: int, reach: int) -> list[float]:
    """Gaussian-weighted average of each reading with its neighbours (by ground distance) within `reach` samples."""
    out = []
    n = len(values)
    for i in range(start, stop):
        r = readings[i]
        sigma = footprint_m(r.alt_m)
        total = weight_sum = 0.0
        for j in range(max(0, i - reach), min(n, i + reach + 1)):
            q = readings[j]
            w = math.exp(-((q.x - r.x) ** 2 + (q.y - r.y) ** 2) / (2 * sigma * sigma))
            total += w * values[j]
            weight_sum += w
        out.append(total / weight_sum)
    return out


class _Channel:
    """One sensor's readings: (optionally) smoothed, then scored against the local background, incrementally. A
    smoothed value is final once `reach` later readings exist; a score once `half_window` later final values do."""

    def __init__(self, half_window: int, guard: int, reach: int) -> None:
        self.half_window, self.guard, self.reach = half_window, guard, reach
        self.raw: list[float] = []
        self._final: list[float] = []  # smoothed values that no longer change
        self._res: list[float] = []
        self._z: list[float] = []

    def scores(self, readings: Sequence[Reading]) -> tuple[list[float], list[float]]:
        n = len(self.raw)
        if self.reach == 0:
            values = self.raw
            final_n = n
        else:
            final_n = max(0, n - self.reach)
            if len(self._final) < final_n:
                self._final += smoothed(readings, self.raw, len(self._final), final_n, self.reach)
            values = self._final + smoothed(readings, self.raw, final_n, n, self.reach)
        stable = max(0, final_n - self.half_window)
        if len(self._z) < stable:
            r, z = robust_scores(values, self.half_window, self.guard, len(self._z), stable)
            self._res += r
            self._z += z
        r_tail, z_tail = robust_scores(values, self.half_window, self.guard, len(self._z), n)
        return self._res + r_tail, self._z + z_tail


def classify_cluster_v2(
    cluster: Cluster,
    readings: Sequence[Reading],
    md_res: Sequence[float],
    md_z: Sequence[float],
    gpr_res: Sequence[float],
    gpr_z: Sequence[float],
    profile: ConditionProfile,
    params: AdaptiveV2Params,
) -> Candidate:
    base = params.as_v1()
    k_md = params.k_md / profile.md_reliability
    k_gpr = params.k_gpr
    idx = [h.index for h in cluster.hits]

    mu = max(md_z[i] for i in idx) / k_md
    rho = max(gpr_z[i] for i in idx) / k_gpr
    md_peak = max(md_res[i] for i in idx)
    gpr_peak = max(gpr_res[i] for i in idx)
    height = statistics.median(readings[i].alt_m for i in idx)
    ref = params.reference_height_m
    correction = (md_gain(height) / md_gain(ref)) / (gpr_gain(height) / gpr_gain(ref))
    ratio = gpr_peak / md_peak * correction if md_peak > 0 else math.inf

    radar_idx = [i for i in idx if gpr_z[i] >= k_gpr]
    depth = None
    if radar_idx:
        twt = statistics.median(readings[i].gpr_twt_ns for i in radar_idx)
        depth = max(0.0, twt * SPEED_OF_LIGHT_M_PER_NS / (2 * math.sqrt(profile.permittivity)))

    md_detected = mu >= 1
    gpr_detected = rho >= 1
    has_body = ratio >= params.body_ratio * profile.gpr_reliability

    if len(idx) < base.min_hits:
        category, reason = Category.CLUTTER, "spike"
    elif depth is not None and depth > base.max_mine_depth_m:
        category, reason = Category.CLUTTER, "deep"
    elif not md_detected and depth is not None and depth > params.max_reflector_depth_m:
        category, reason = Category.CLUTTER, "deep_reflector"
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

    cap = base.evidence_cap
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
        explanation=_describe_v2(reason, mu, rho, ratio, depth, height, profile, params),
        features={
            "version": VERSION,
            "reason": reason,
            "md_evidence": round(mu, 3),
            "gpr_evidence": round(rho, 3),
            "body_ratio": round(ratio, 3) if math.isfinite(ratio) else None,
            "body_ratio_min": round(params.body_ratio * profile.gpr_reliability, 3),
            "height_m": round(height, 2),
            "height_correction": round(correction, 3),
            "md_threshold_k": round(k_md, 3),
            "gpr_threshold_k": round(k_gpr, 3),
            "md_reliability": profile.md_reliability,
            "gpr_reliability": profile.gpr_reliability,
            "soil_type": profile.soil_type,
            "evidence": round(evidence, 3),
        },
    )


def _describe_v2(
    reason: str,
    mu: float,
    rho: float,
    ratio: float,
    depth: float | None,
    height: float,
    p: ConditionProfile,
    params: AdaptiveV2Params,
) -> str:
    sensors = f"Metal detector at {mu:.1f}x and radar at {rho:.1f}x their local adaptive thresholds"
    depth_text = f"; estimated depth {depth:.2f} m" if depth is not None else ""
    soil = (
        f"Soil: {p.soil_label} (metal-detector reliability {p.md_reliability:.2f}, "
        f"radar reliability {p.gpr_reliability:.2f}); sensor height {height:.2f} m."
    )
    verdicts = {
        "spike": "Isolated single-sample response, treated as noise.",
        "deep": "Reflector deeper than typical burial depth: likely a natural structure.",
        "deep_reflector": (
            f"Radar reflector without metal deeper than {params.max_reflector_depth_m:.2f} m: likely a stone or a "
            "natural structure."
        ),
        "metal_with_body": (
            f"Metal response with a matching radar reflection (height-corrected body ratio {ratio:.2f}): "
            "consistent with a buried object with metal content."
        ),
        "metal_without_body_trusted": (
            f"Metal response with little radar reflection (height-corrected body ratio {ratio:.2f}) in a soil "
            "where radar penetrates well: consistent with small metal fragments."
        ),
        "metal_without_body_untrusted": (
            f"Metal response with little radar reflection (height-corrected body ratio {ratio:.2f}), but radar is "
            "attenuated in this soil, so the object cannot be ruled out."
        ),
        "metal_weak_radar": "Metal response with a weak radar reflection.",
        "non_metallic_reflector": (
            "Shallow radar reflector without a significant metal response: consistent with a low-metal or plastic "
            "object, or a stone."
        ),
    }
    return f"{soil} {sensors}{depth_text}. {verdicts[reason]}"


def reach_samples(context: SurveyContext) -> int:
    """How many readings on each side the matched filter looks at: three footprints along the track."""
    spacing = max(context.speed_mps * context.sample_period_s, 1e-3)
    return max(1, math.ceil(3 * footprint_m(context.altitude_m) / spacing))


class AdaptiveDetectorV2:
    """Streaming version 2 detector: add readings as they arrive, ask for candidates any time."""

    def __init__(self, context: SurveyContext, params: AdaptiveV2Params) -> None:
        self.params = params
        self.profile = condition_profile(context, params.as_v1())
        reach = reach_samples(context) if params.smooth else 0
        self._readings: list[Reading] = []
        self._md = _Channel(self.profile.half_window, self.profile.guard, reach)
        self._gpr = _Channel(self.profile.half_window, self.profile.guard, reach)

    def add(self, readings: Iterable[Reading]) -> None:
        new = list(readings)
        self._readings.extend(new)
        self._md.raw.extend(r.md for r in new)
        self._gpr.raw.extend(r.gpr_amp for r in new)

    def scores(self) -> tuple[list[float], list[float], list[float], list[float]]:
        md_res, md_z = self._md.scores(self._readings)
        gpr_res, gpr_z = self._gpr.scores(self._readings)
        return md_res, md_z, gpr_res, gpr_z

    def candidates(self) -> list[Candidate]:
        return classify_v2(self._readings, *self.scores(), self.profile, self.params)


def classify_v2(
    readings: Sequence[Reading],
    md_res: Sequence[float],
    md_z: Sequence[float],
    gpr_res: Sequence[float],
    gpr_z: Sequence[float],
    profile: ConditionProfile,
    params: AdaptiveV2Params,
) -> list[Candidate]:
    k_md = params.k_md / profile.md_reliability
    k_gpr = params.k_gpr
    hits = []
    for i, r in enumerate(readings):
        score = max(md_z[i] / k_md, gpr_z[i] / k_gpr)
        if score >= 1:
            hits.append(Hit(r, score, i))
    return [
        classify_cluster_v2(c, readings, md_res, md_z, gpr_res, gpr_z, profile, params)
        for c in cluster_hits(hits, profile.link_radius_m)
    ]


def detect_adaptive_v2(
    readings: Sequence[Reading], context: SurveyContext, params: AdaptiveV2Params
) -> list[Candidate]:
    detector = AdaptiveDetectorV2(context, params)
    detector.add(readings)
    return detector.candidates()
