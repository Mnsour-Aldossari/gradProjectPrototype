"""Spatial grouping of hits so one buried object becomes one candidate."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from .types import Hit


@dataclass(frozen=True)
class Cluster:
    hits: tuple[Hit, ...]

    @property
    def center(self) -> tuple[float, float]:
        total = sum(h.score for h in self.hits)
        if total <= 0:
            n = len(self.hits)
            return sum(h.reading.x for h in self.hits) / n, sum(h.reading.y for h in self.hits) / n
        x = sum(h.reading.x * h.score for h in self.hits) / total
        y = sum(h.reading.y * h.score for h in self.hits) / total
        return x, y

    @property
    def peak(self) -> Hit:
        return max(self.hits, key=lambda h: h.score)

    @property
    def extent_m(self) -> float:
        cx, cy = self.center
        return max(math.hypot(h.reading.x - cx, h.reading.y - cy) for h in self.hits)


def cluster_hits(hits: Sequence[Hit], link_radius_m: float) -> list[Cluster]:
    """Single-linkage clustering: hits closer than link_radius_m share a cluster."""
    if not hits:
        return []
    parent = list(range(len(hits)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, h in enumerate(hits):
        grid[(math.floor(h.reading.x / link_radius_m), math.floor(h.reading.y / link_radius_m))].append(i)

    for (cx, cy), members in grid.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((cx + dx, cy + dy), ()):
                    for i in members:
                        if i < j:
                            a, b = hits[i].reading, hits[j].reading
                            if math.hypot(a.x - b.x, a.y - b.y) <= link_radius_m:
                                parent[find(i)] = find(j)

    groups: dict[int, list[Hit]] = defaultdict(list)
    for i, h in enumerate(hits):
        groups[find(i)].append(h)
    clusters = [Cluster(tuple(g)) for g in groups.values()]
    clusters.sort(key=lambda c: min(h.reading.t_s for h in c.hits))
    return clusters
