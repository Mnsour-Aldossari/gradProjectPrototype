"""Survey path planning and simple UAV kinematics."""

from __future__ import annotations

import math
import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from .geo import XY, BBox

ALTITUDE_JITTER_M = 0.03


@dataclass(frozen=True)
class FlightSample:
    t_s: float
    x: float
    y: float
    alt_m: float  # height above ground
    v_east: float
    v_north: float
    heading_deg: float  # compass heading, 0 = north, clockwise
    battery_pct: float
    waypoint_index: int  # index of the waypoint currently being flown to
    progress: float  # fraction of path length flown, 0..1


def lawnmower_path(bbox: BBox, line_spacing_m: float) -> list[XY]:
    """East-west survey lines covering the box; no point is further than half a spacing from a line."""
    xmin, ymin, xmax, ymax = bbox
    n_lines = max(1, math.ceil((ymax - ymin) / line_spacing_m))
    step = (ymax - ymin) / n_lines
    waypoints: list[XY] = []
    for k in range(n_lines):
        y = ymin + (k + 0.5) * step
        if k % 2 == 0:
            waypoints += [(xmin, y), (xmax, y)]
        else:
            waypoints += [(xmax, y), (xmin, y)]
    return waypoints


def path_length(waypoints: Sequence[XY]) -> float:
    return sum(math.dist(a, b) for a, b in zip(waypoints, waypoints[1:]))


def fly(
    waypoints: Sequence[XY],
    altitude_m: float,
    speed_mps: float,
    dt_s: float,
    *,
    battery_drain_pct_per_s: float,
    rng: random.Random,
) -> Iterator[FlightSample]:
    """Constant-speed flight along the waypoints, one sample every dt_s."""
    seg_lengths = [math.dist(a, b) for a, b in zip(waypoints, waypoints[1:])]
    total = sum(seg_lengths)
    if total <= 0:
        raise ValueError("flight path has zero length")
    step = speed_mps * dt_s
    n_steps = math.ceil(total / step)

    seg = 0
    seg_start = 0.0
    for k in range(n_steps + 1):
        s = min(k * step, total)
        while seg < len(seg_lengths) - 1 and s > seg_start + seg_lengths[seg]:
            seg_start += seg_lengths[seg]
            seg += 1
        (x0, y0), (x1, y1) = waypoints[seg], waypoints[seg + 1]
        length = seg_lengths[seg]
        u = (s - seg_start) / length if length > 0 else 1.0
        dir_e = (x1 - x0) / length if length > 0 else 0.0
        dir_n = (y1 - y0) / length if length > 0 else 0.0
        moving = k < n_steps
        t = k * dt_s
        yield FlightSample(
            t_s=t,
            x=x0 + (x1 - x0) * u,
            y=y0 + (y1 - y0) * u,
            alt_m=altitude_m + rng.gauss(0.0, ALTITUDE_JITTER_M),
            v_east=dir_e * speed_mps if moving else 0.0,
            v_north=dir_n * speed_mps if moving else 0.0,
            heading_deg=math.degrees(math.atan2(dir_e, dir_n)) % 360,
            battery_pct=max(0.0, 100.0 - battery_drain_pct_per_s * t),
            waypoint_index=seg + 1,
            progress=s / total,
        )
