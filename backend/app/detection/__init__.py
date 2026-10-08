"""Detection and classification library.

Pure Python with no dependency on the web framework or database, so it can
be unit-tested on its own and later wrapped as a ROS 2 node or another service.
Outputs are potential detections for verification by trained personnel.
"""

from collections.abc import Sequence

from .adaptive import AdaptiveDetector, detect_adaptive
from .adaptive_v2 import AdaptiveDetectorV2, detect_adaptive_v2
from .baseline import BaselineConfig, detect_baseline
from .context import SurveyContext
from .params import FROZEN_PARAMS, AdaptiveParams
from .params_v2 import FROZEN_PARAMS_V2
from .types import CATEGORY_LABELS, Candidate, Category, Hit, Reading


# The detector the app runs while a mission flies (and the ROS 2 detector node): version 2 since 2026-10-08. Its
# evaluation did not meet one condition of its adoption rule (6 more false alarms than version 1 over 450 surveys,
# for 10 points more mines found); the project owner chose to adopt it anyway (docs/EVALUATION_RESULTS_V2.md).
# Version 1 stays for the official evaluation and the Evaluation page.
# Version 2's thresholds in version 1's form, for what shares version 1's code (the condition profile).
LIVE_PARAMS = FROZEN_PARAMS_V2.as_v1()


def live_detector(context: SurveyContext) -> AdaptiveDetectorV2:
    return AdaptiveDetectorV2(context, FROZEN_PARAMS_V2)


def detect_live(readings: Sequence[Reading], context: SurveyContext) -> list[Candidate]:
    return detect_adaptive_v2(readings, context, FROZEN_PARAMS_V2)


__all__ = [
    "CATEGORY_LABELS",
    "FROZEN_PARAMS",
    "LIVE_PARAMS",
    "AdaptiveDetector",
    "AdaptiveDetectorV2",
    "AdaptiveParams",
    "BaselineConfig",
    "Candidate",
    "Category",
    "Hit",
    "Reading",
    "SurveyContext",
    "detect_adaptive",
    "detect_baseline",
    "detect_live",
    "live_detector",
]
