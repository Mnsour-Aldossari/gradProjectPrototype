"""Frozen parameters of the version 2 adaptive detector (adaptive_v2.py).

FROZEN on 2026-10-08: calibrated on tuning seeds 1000-1019 at five survey settings (scripts/calibrate_v2.py,
docs/calibration_result_v2.json), before any run on the version 2 evaluation seeds. Do not change after evaluation
results have been seen (docs/EVALUATION_PROTOCOL_V2.md).
"""

from __future__ import annotations

from .adaptive_v2 import AdaptiveV2Params
from .params import FROZEN_PARAMS

FROZEN_PARAMS_V2 = AdaptiveV2Params(
    k_md=3.0,
    k_gpr=4.0,
    body_ratio=0.1,
    max_reflector_depth_m=0.12,
    smooth=False,  # the matched filter was tried and not chosen: fewer mines found within version 1's false alarms
    reliability=dict(FROZEN_PARAMS.reliability),  # version 1's, not calibrated again
)
