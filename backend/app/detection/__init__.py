"""Detection and classification library.

Pure Python with no dependency on the web framework or database, so it can
be unit-tested on its own and later wrapped as a ROS 2 node or another service.
Outputs are potential detections for verification by trained personnel.
"""

from .baseline import BaselineConfig, detect_baseline
from .types import CATEGORY_LABELS, Candidate, Category, Hit, Reading

__all__ = [
    "CATEGORY_LABELS",
    "BaselineConfig",
    "Candidate",
    "Category",
    "Hit",
    "Reading",
    "detect_baseline",
]
