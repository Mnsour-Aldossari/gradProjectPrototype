"""Plain data types shared by the detection algorithms.

Positions are local metres (x east, y north) so the algorithms stay free of
geodesy, web and database concerns.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class Category(StrEnum):
    HIGH = "high"
    SUSPECT = "suspect"
    CLUTTER = "clutter"


# Every output is a *potential* detection; final verification is done by trained personnel.
CATEGORY_LABELS: dict[Category, str] = {
    Category.HIGH: "Potential detection - high priority",
    Category.SUSPECT: "Suspicious - needs verification",
    Category.CLUTTER: "Likely clutter",
}


@dataclass(frozen=True)
class Reading:
    t_s: float
    x: float
    y: float
    alt_m: float  # sensor height above ground
    md: float
    gpr_amp: float
    gpr_twt_ns: float


@dataclass(frozen=True)
class Hit:
    reading: Reading
    score: float


@dataclass(frozen=True)
class Candidate:
    x: float
    y: float
    category: Category
    confidence: float  # 0..1
    peak_md: float
    peak_gpr: float
    est_depth_m: float | None
    n_hits: int
    method: str
    explanation: str
    features: Mapping[str, float] = field(default_factory=dict)
