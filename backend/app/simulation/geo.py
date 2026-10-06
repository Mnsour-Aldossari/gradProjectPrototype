"""Local flat-earth frame for converting between lat/lon and metres.

Survey areas are a few hundred metres across at most, so an equirectangular
projection around the area centre is accurate to well under a centimetre.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_008.8

LatLon = tuple[float, float]
XY = tuple[float, float]
BBox = tuple[float, float, float, float]  # xmin, ymin, xmax, ymax


@dataclass(frozen=True)
class LocalFrame:
    """East (x) / North (y) metres around a reference point."""

    lat0: float
    lon0: float

    @classmethod
    def centred_on(cls, polygon: Sequence[Sequence[float]]) -> LocalFrame:
        lats = [p[0] for p in polygon]
        lons = [p[1] for p in polygon]
        return cls(sum(lats) / len(lats), sum(lons) / len(lons))

    def to_xy(self, lat: float, lon: float) -> XY:
        x = math.radians(lon - self.lon0) * EARTH_RADIUS_M * math.cos(math.radians(self.lat0))
        y = math.radians(lat - self.lat0) * EARTH_RADIUS_M
        return x, y

    def to_latlon(self, x: float, y: float) -> LatLon:
        lat = self.lat0 + math.degrees(y / EARTH_RADIUS_M)
        lon = self.lon0 + math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(self.lat0))))
        return lat, lon


def bounding_box(points: Sequence[XY]) -> BBox:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def point_in_polygon(x: float, y: float, polygon: Sequence[XY]) -> bool:
    """Ray-casting test; points exactly on an edge may go either way."""
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cross:
                inside = not inside
    return inside


def crossings_at(y: float, polygon: Sequence[XY]) -> list[tuple[float, float]]:
    """The stretches [x0, x1] of the horizontal line at y that lie inside the polygon, left to right."""
    xs: list[float] = []
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    xs.sort()
    return [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]


def polygon_area(polygon: Sequence[XY]) -> float:
    n = len(polygon)
    return abs(sum(polygon[i][0] * polygon[(i + 1) % n][1] - polygon[(i + 1) % n][0] * polygon[i][1] for i in range(n))) / 2


def _segments_cross(a: XY, b: XY, c: XY, d: XY) -> bool:
    def orient(p: XY, q: XY, r: XY) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on(p: XY, q: XY, r: XY) -> bool:  # r on segment pq, given collinear
        return min(p[0], q[0]) - 1e-9 <= r[0] <= max(p[0], q[0]) + 1e-9 and min(p[1], q[1]) - 1e-9 <= r[1] <= max(
            p[1], q[1]
        ) + 1e-9

    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0) and 0 not in (o1, o2, o3, o4):
        return True
    eps = 1e-9
    return (
        (abs(o1) < eps and on(a, b, c))
        or (abs(o2) < eps and on(a, b, d))
        or (abs(o3) < eps and on(c, d, a))
        or (abs(o4) < eps and on(c, d, b))
    )


def is_simple(polygon: Sequence[XY]) -> bool:
    """True if no two edges cross or touch, other than neighbours at their shared corner."""
    n = len(polygon)
    edges = [(polygon[i], polygon[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue  # neighbours share a corner
            if _segments_cross(*edges[i], *edges[j]):
                return False
    return True
