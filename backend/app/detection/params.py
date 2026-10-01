"""Tunable parameters of the adaptive detector.

Values marked "calibrated" are chosen once on the tuning seeds only (see
docs/EVALUATION_PROTOCOL.md and scripts/calibrate.py) and then frozen.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SoilReliability:
    md: float  # 0..1; low = soil disturbs the metal detector (raises its threshold)
    gpr: float  # 0..1; low = radar is attenuated, so a missing reflection is weak evidence


@dataclass(frozen=True)
class AdaptiveParams:
    k_md: float  # robust z-score threshold for the metal detector (calibrated)
    k_gpr: float  # robust z-score threshold for the GPR (calibrated)
    body_ratio: float  # min GPR/MD residual ratio for a metal object with a mine-sized body (calibrated)
    reliability: Mapping[str, SoilReliability] = field(default_factory=dict)  # per soil type (calibrated)

    # Design constants (not calibrated)
    background_window_m: float = 20.0  # along-track window for the local background estimate
    guard_m: float = 2.0  # along-track guard zone excluded from the background (CFAR guard cells)
    max_mine_depth_m: float = 0.30  # deeper reflectors are treated as natural structures
    radar_trust: float = 0.75  # gpr reliability at/above which a missing reflection counts as evidence
    min_hits: int = 2  # isolated single-sample responses are noise
    evidence_cap: float = 3.0  # cap on normalised evidence per sensor

    def soil(self, soil_type: str) -> SoilReliability:
        return self.reliability.get(soil_type, SoilReliability(md=1.0, gpr=1.0))


# FROZEN on 2026-10-01: calibrated on tuning seeds 1000-1019 (docs/calibration_result.json).
# Do not change after evaluation results have been seen (docs/EVALUATION_PROTOCOL.md).
FROZEN_PARAMS = AdaptiveParams(
    k_md=4.0,
    k_gpr=5.0,
    body_ratio=0.1,
    reliability={
        "dry_sand": SoilReliability(md=0.5, gpr=1.0),
        "wet_clay": SoilReliability(md=0.5, gpr=0.75),
        "mineralized_rocky": SoilReliability(md=0.5, gpr=1.0),
    },
)
