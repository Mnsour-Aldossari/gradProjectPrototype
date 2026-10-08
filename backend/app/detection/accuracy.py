"""How well the detector is expected to do with given survey settings: the estimate shown while planning.

scripts/accuracy_table.py flies the standard test field on a grid of sensor heights, speeds and lane spacings, for
each soil, on its own seeds, and counts what the app's detector found (accuracy_table.json). Here a setting between
grid points gets its counts interpolated (trilinear; outside the grid, the nearest edge), and the rates follow from
them. Simulated data: the estimate compares settings inside the simulation and does not predict field performance.
"""

from __future__ import annotations

import bisect
import json
import math
from dataclasses import dataclass
from functools import cache
from pathlib import Path

TABLE_PATH = Path(__file__).with_name("accuracy_table.json")
ALTITUDES_M = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0)
SPEEDS_MPS = (0.5, 1.0, 2.0, 3.0, 5.0)
SPACINGS_M = (0.5, 1.0, 1.5, 2.0, 3.0, 5.0)
COUNTS = ("surveys", "targets", "found", "false_alarms", "low_metal", "low_metal_found")


@dataclass(frozen=True)
class Estimate:
    soil_type: str
    altitude_m: float
    speed_mps: float
    line_spacing_m: float
    recall: float  # share of the mines found (reported as high priority or needs verification)
    recall_margin: float  # about 95 % of the time the share lies within recall ± this, from the surveys behind it
    precision: float  # share of the reports that are mines
    false_alarms_per_ha: float
    low_metal_recall: float  # share of the low-metal mines found, the hardest
    surveys: int  # simulated surveys behind the nearest grid point
    seeds: tuple[int, int]
    method: str


@dataclass(frozen=True)
class _Table:
    method: str
    seeds: tuple[int, int]
    area_ha: float
    axes: tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]
    cells: dict[tuple[str, float, float, float], dict[str, float]]


@cache
def _table(path: Path = TABLE_PATH) -> _Table | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    cells = {
        (r["soil"], r["altitude_m"], r["speed_mps"], r["line_spacing_m"]): {k: float(r[k]) for k in COUNTS}
        for r in data["rows"]
    }
    axes = (tuple(data["altitudes_m"]), tuple(data["speeds_mps"]), tuple(data["spacings_m"]))
    return _Table(data["method"], tuple(data["seeds"]), data["survey_area_m2"] / 10_000, axes, cells)


def _bracket(axis: tuple[float, ...], value: float) -> list[tuple[float, float]]:
    """The grid points around value with their weights; the nearest edge outside the grid."""
    if value <= axis[0]:
        return [(axis[0], 1.0)]
    if value >= axis[-1]:
        return [(axis[-1], 1.0)]
    i = bisect.bisect_right(axis, value)
    lo, hi = axis[i - 1], axis[i]
    w = (value - lo) / (hi - lo)
    return [(lo, 1 - w), (hi, w)]


def _nearest(axis: tuple[float, ...], value: float) -> float:
    return min(axis, key=lambda a: abs(a - value))


def estimate(
    soil_type: str, altitude_m: float, speed_mps: float, line_spacing_m: float, path: Path = TABLE_PATH
) -> Estimate | None:
    """None when there is no table, or nothing for this soil."""
    table = _table(path)
    if table is None:
        return None
    alts, speeds, spacings = table.axes
    counts = dict.fromkeys(COUNTS, 0.0)
    for a, wa in _bracket(alts, altitude_m):
        for s, ws in _bracket(speeds, speed_mps):
            for d, wd in _bracket(spacings, line_spacing_m):
                cell = table.cells.get((soil_type, a, s, d))
                if cell is None:
                    return None
                for k in COUNTS:
                    counts[k] += wa * ws * wd * cell[k]
    nearest = table.cells[(soil_type, _nearest(alts, altitude_m), _nearest(speeds, speed_mps),
                           _nearest(spacings, line_spacing_m))]  # fmt: skip
    recall = counts["found"] / counts["targets"] if counts["targets"] else 0.0
    margin = 1.96 * math.sqrt(recall * (1 - recall) / nearest["targets"]) if nearest["targets"] else 0.0
    reported = counts["found"] + counts["false_alarms"]
    return Estimate(
        soil_type=soil_type,
        altitude_m=altitude_m,
        speed_mps=speed_mps,
        line_spacing_m=line_spacing_m,
        recall=round(recall, 3),
        recall_margin=round(margin, 3),
        precision=round(counts["found"] / reported, 3) if reported else 0.0,
        false_alarms_per_ha=round(counts["false_alarms"] / counts["surveys"] / table.area_ha, 2),
        low_metal_recall=round(counts["low_metal_found"] / counts["low_metal"], 3) if counts["low_metal"] else 0.0,
        surveys=int(nearest["surveys"]),
        seeds=table.seeds,
        method=table.method,
    )
