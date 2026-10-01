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
