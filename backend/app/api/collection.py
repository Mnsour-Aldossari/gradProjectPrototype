"""Sensor collection: how well a survey's MD/GPR readings cover its lanes, kept apart from how the flight ended.

A flight can end well with readings missing (Flight: Completed, Sensors: Partial), and a flight can fail after the
lanes were all read (Flight: Failed, Sensors: Complete). A sensor that stops sending never stops the flight: frames
without a reading only leave a gap in the lanes.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Sequence
from dataclasses import dataclass

from sqlmodel import Session, select

from app.models import Mission, SensorReading, TelemetryPoint
from app.simulation import SimulationConfig, plan_survey
from app.simulation.geo import XY

COMPLETE, PARTIAL, FAILED, NOT_STARTED = "complete", "partial", "failed", "not_started"
LONG_PAUSE_S = 60.0  # a pause longer than this (real time) means the lanes were not read in one go
GAP_SAMPLES = 3  # more than this many sample spacings along a lane without a reading is a gap
MIN_GAP_M = 1.0
SURVEY_DONE = 0.999  # survey progress from which the last lane counts as flown


@dataclass(frozen=True)
class Collection:
    status: str  # complete | partial | failed | not_started
    readings: int
    coverage: float | None  # share of the lanes' length read without gaps, 0..1; None: nothing was flown
    note: str | None  # why it is not complete


def lane_coverage(
    waypoints_xy: Sequence[XY], points: Sequence[XY], gap_m: float
) -> tuple[float, list[tuple[int, float]]]:
    """The share of the lanes' length with readings no further apart than gap_m, and the gaps as (lane number from 1,
    length in m). The lanes are the waypoint pairs of survey_lanes, east-west; a reading counts for the nearest."""
    lanes = [(waypoints_xy[i], waypoints_xy[i + 1]) for i in range(0, len(waypoints_xy) - 1, 2)]
    if not lanes:
        return 0.0, []
    by_y = sorted(range(len(lanes)), key=lambda k: lanes[k][0][1])
    ys = [lanes[k][0][1] for k in by_y]
    along: list[list[float]] = [[] for _ in lanes]
    for x, y in points:
        i = bisect.bisect_left(ys, y)
        near = {ys[j] for j in (i - 1, i) if 0 <= j < len(ys)}
        lane_y = min(near, key=lambda v: abs(v - y))
        # Pieces of one lane share its y (a concave outline): the piece nearest along x.
        k = min((k for k in by_y if lanes[k][0][1] == lane_y), key=lambda k: _outside(x, lanes[k]))
        (x0, _), (x1, _) = lanes[k]
        along[k].append(min(max((x - x0) / (x1 - x0), 0.0), 1.0) * abs(x1 - x0) if x1 != x0 else 0.0)

    covered, total, gaps = 0.0, 0.0, []
    for k, ((x0, _), (x1, _)) in enumerate(lanes):
        length = abs(x1 - x0)
        total += length
        widest, previous = 0.0, 0.0
        for s in [*sorted(along[k]), length]:
            step = s - previous
            if step <= gap_m:
                covered += step
            else:
                widest = max(widest, step)
            previous = s
        if widest:
            gaps.append((k + 1, widest))
    return (covered / total if total else 0.0), gaps


def _outside(x: float, lane: tuple[XY, XY]) -> float:
    """How far x is beyond the ends of a lane (0 within it)."""
    (x0, _), (x1, _) = lane
    return max(0.0, min(x0, x1) - x, x - max(x0, x1))


def _duration(seconds: float) -> str:
    minutes, s = divmod(round(seconds), 60)
    return f"{minutes} min {s} s" if minutes else f"{s} s"


def _numbers(values: list[int]) -> str:
    shown = [str(v) for v in values[:6]] + (["…"] if len(values) > 6 else [])
    return ", ".join(shown[:-1]) + " and " + shown[-1] if len(shown) > 1 else shown[0]


def assess(
    waypoints_xy: Sequence[XY],
    points: Sequence[XY],
    *,
    flew: bool,
    sample_spacing_m: float,
    ended: str | None = None,
    longest_pause_s: float = 0.0,
) -> Collection:
    """points: where the readings were taken (local x, y). flew: telemetry came from the UAV. ended: why the survey
    did not reach its last lane, if it did not. longest_pause_s: the longest pause, in real time."""
    if not flew:
        return Collection(NOT_STARTED, 0, None, None)
    if not points:
        return Collection(FAILED, 0, 0.0, "No sensor readings were received")
    coverage, gaps = lane_coverage(waypoints_xy, points, max(MIN_GAP_M, GAP_SAMPLES * sample_spacing_m))
    reasons = []
    if ended:
        reasons.append(ended)
    elif gaps:
        lanes = [lane for lane, _ in gaps]
        longest = max(length for _, length in gaps)
        reasons.append(f"Gaps in the readings on lane{'s' if len(lanes) > 1 else ''} {_numbers(lanes)} "
                       f"(the longest {longest:.1f} m)")
    if longest_pause_s > LONG_PAUSE_S:
        reasons.append(f"Paused for {_duration(longest_pause_s)} (over {_duration(LONG_PAUSE_S)}): the lanes were not "
                       "read in one go")
    return Collection(PARTIAL if reasons else COMPLETE, len(points), round(coverage, 4), "; ".join(reasons) or None)


def assess_stored(session: Session, mission: Mission, ended: str) -> Collection:
    """From the readings stored for a mission whose run stopped without assessing them (the server stopped).
    ended: why the survey stopped, if it had not reached its last lane."""
    plan = plan_survey(mission.area, mission.line_spacing_m)
    rows = session.exec(select(SensorReading.lat, SensorReading.lon).where(SensorReading.mission_id == mission.id))
    points = [plan.frame.to_xy(lat, lon) for lat, lon in rows]
    flew = bool(points) or session.exec(
        select(TelemetryPoint.id).where(TelemetryPoint.mission_id == mission.id).limit(1)
    ).first() is not None
    return assess(
        plan.waypoints_xy,
        points,
        flew=flew,
        sample_spacing_m=mission.speed_mps * SimulationConfig.dt_s,
        ended=ended if mission.progress < SURVEY_DONE else None,
    )


def apply(mission: Mission, collection: Collection) -> None:
    mission.sensor_collection = collection.status
    mission.sensor_reading_count = collection.readings
    mission.sensor_coverage = collection.coverage
    mission.sensor_note = collection.note
