"""Detection and classification library.

Pure Python with no dependency on the web framework or database, so it can
be unit-tested on its own and later wrapped as a ROS 2 node or another service.
Outputs are potential detections for verification by trained personnel.
"""

from .adaptive import AdaptiveDetector, detect_adaptive
from .baseline import BaselineConfig, detect_baseline
from .context import SurveyContext
from .params import FROZEN_PARAMS, AdaptiveParams
from .types import CATEGORY_LABELS, Candidate, Category, Hit, Reading

__all__ = [
    "CATEGORY_LABELS",
    "FROZEN_PARAMS",
    "AdaptiveDetector",
    "AdaptiveParams",
    "BaselineConfig",
    "Candidate",
    "Category",
    "Hit",
    "Reading",
    "SurveyContext",
    "detect_adaptive",
    "detect_baseline",
]
