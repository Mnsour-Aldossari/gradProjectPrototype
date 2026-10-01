"""Scoring candidates against known (simulated) ground truth.

A candidate counts as *reported* when its category is HIGH or SUSPECT: both
would send personnel to verify the location. CLUTTER is not reported.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from .types import Candidate, Category

REPORTED = frozenset({Category.HIGH, Category.SUSPECT})


@dataclass(frozen=True)
class TruthObject:
    x: float
    y: float
    kind: str
    is_target: bool  # True for mines


@dataclass
class EvalCounts:
    targets: int = 0
    tp: int = 0
    fp: int = 0
    fp_by_cause: Counter = field(default_factory=Counter)  # object kind, "duplicate" or "background"
    # per object kind: "reported" / "clutter" (only clutter candidates nearby) / "none" (nothing nearby)
    outcomes: dict[str, Counter] = field(default_factory=dict)

    @property
    def fn(self) -> int:
        return self.targets - self.tp

    @property
    def recall(self) -> float:
        return self.tp / self.targets if self.targets else 0.0

    @property
    def precision(self) -> float:
        reported = self.tp + self.fp
        return self.tp / reported if reported else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def add(self, other: EvalCounts) -> EvalCounts:
        self.targets += other.targets
        self.tp += other.tp
        self.fp += other.fp
        self.fp_by_cause.update(other.fp_by_cause)
        for kind, counter in other.outcomes.items():
            self.outcomes.setdefault(kind, Counter()).update(counter)
        return self

    def to_dict(self) -> dict:
        return {
            "targets": self.targets,
            "tp": self.tp,
            "fn": self.fn,
            "fp": self.fp,
            "recall": round(self.recall, 4),
            "precision": round(self.precision, 4),
            "f1": round(self.f1, 4),
            "fp_by_cause": dict(self.fp_by_cause),
            "outcomes": {k: dict(v) for k, v in self.outcomes.items()},
        }


def evaluate(candidates: Sequence[Candidate], truths: Sequence[TruthObject], match_radius_m: float) -> EvalCounts:
    counts = EvalCounts(targets=sum(t.is_target for t in truths))
    reported = sorted((c for c in candidates if c.category in REPORTED), key=lambda c: -c.confidence)
    matched: set[int] = set()

    for c in reported:
        nearby = sorted(
            (math.hypot(c.x - t.x, c.y - t.y), i) for i, t in enumerate(truths)
        )
        nearby = [(d, i) for d, i in nearby if d <= match_radius_m]
        target = next((i for _, i in nearby if truths[i].is_target and i not in matched), None)
        if target is not None:
            matched.add(target)
            counts.tp += 1
            continue
        counts.fp += 1
        if not nearby:
            counts.fp_by_cause["background"] += 1
        elif truths[nearby[0][1]].is_target:
            counts.fp_by_cause["duplicate"] += 1
        else:
            counts.fp_by_cause[truths[nearby[0][1]].kind] += 1

    for t in truths:
        near = [c for c in candidates if math.hypot(c.x - t.x, c.y - t.y) <= match_radius_m]
        if any(c.category in REPORTED for c in near):
            outcome = "reported"
        elif near:
            outcome = "clutter"
        else:
            outcome = "none"
        counts.outcomes.setdefault(t.kind, Counter())[outcome] += 1
    return counts
