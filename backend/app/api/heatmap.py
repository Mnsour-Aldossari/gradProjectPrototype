"""The sensor readings of a mission as a grid, for the heatmap on the mission map.

The lanes run east-west, so each grid row is a lane (the strip the sensors read between it and the next) and each
column a short piece of it. A cell holds the strongest reading in it, so a small object is not averaged away when
many readings share a cell. Values are divided by a fixed full scale per sensor (the same for every mission and
while the UAV flies): 0 is no response, 1 a reading at or above the full scale. Simulated, arbitrary units.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from fastapi import APIRouter
from sqlmodel import select

from app.models import SensorReading
from app.simulation import plan_survey
from app.simulation.geo import bounding_box

from .deps import CurrentUser, SessionDep
from .missions import get_mission_or_404

router = APIRouter(prefix="/api/missions", tags=["missions"])

# A reading this strong is the top of the colour scale. Picked from the simulator's readings on the standard survey:
# the soil's background stays low (at most about MD 0.3 and GPR 0.06, in mineralised soil), buried metal reaches it.
MD_FULL_SCALE = 1.0
GPR_FULL_SCALE = 0.4
CELL_M = 0.5  # along a lane
MAX_ROWS = 200  # more lanes than this share a row
MAX_CELLS = 20_000  # wider cells beyond this, so a big survey stays a small download


@dataclass(frozen=True)
class SensorGrid:
    bounds: tuple[tuple[float, float], tuple[float, float]]  # (south, west), (north, east)
    rows: int
    cols: int
    cell_m: tuple[float, float]  # width (east-west), height (north-south)
    md: list[float | None]  # row by row from the north-west corner; None: no reading in the cell
    gpr: list[float | None]
    readings: int


def sensor_grid(
    area: Sequence[Sequence[float]], line_spacing_m: float, readings: Iterable[tuple[float, float, float, float]]
) -> SensorGrid:
    """readings: (lat, lon, md, gpr_amp). The grid follows the survey's lanes, in the frame the flight used."""
    plan = plan_survey(area, line_spacing_m)
    xmin, ymin, xmax, ymax = bounding_box(plan.area_xy)
    width, height = xmax - xmin, ymax - ymin
    lanes = max(1, math.ceil(height / line_spacing_m))
    per_row = math.ceil(lanes / MAX_ROWS)
    rows = math.ceil(lanes / per_row)
    cell_h = height / lanes * per_row
    cols = max(1, min(math.ceil(width / CELL_M), MAX_CELLS // rows))
    cell_w = width / cols

    md: list[float | None] = [None] * (rows * cols)
    gpr: list[float | None] = [None] * (rows * cols)
    count = 0
    for lat, lon, m, g in readings:
        x, y = plan.frame.to_xy(lat, lon)
        col, row = math.floor((x - xmin) / cell_w), math.floor((ymax - y) / cell_h)
        # PX4 can read a little outside the outline while it turns; further out than a cell is not on the survey.
        if not (-1 <= col <= cols and -1 <= row <= rows):
            continue
        i = min(max(row, 0), rows - 1) * cols + min(max(col, 0), cols - 1)
        md[i] = m if md[i] is None else max(md[i], m)
        gpr[i] = g if gpr[i] is None else max(gpr[i], g)
        count += 1

    def scaled(values: list[float | None], full: float) -> list[float | None]:
        return [None if v is None else round(min(1.0, max(0.0, v) / full), 3) for v in values]

    south_west = plan.frame.to_latlon(xmin, ymax - rows * cell_h)
    north_east = plan.frame.to_latlon(xmax, ymax)
    return SensorGrid(
        bounds=(south_west, north_east),
        rows=rows,
        cols=cols,
        cell_m=(round(cell_w, 3), round(cell_h, 3)),
        md=scaled(md, MD_FULL_SCALE),
        gpr=scaled(gpr, GPR_FULL_SCALE),
        readings=count,
    )


@router.get("/{mission_id}/heatmap")
def get_heatmap(mission_id: int, session: SessionDep, _: CurrentUser) -> dict:
    """The mission's MD and GPR readings so far as a grid of normalized peaks (simulated data)."""
    mission = get_mission_or_404(session, mission_id)
    rows = session.exec(
        select(SensorReading.lat, SensorReading.lon, SensorReading.md, SensorReading.gpr_amp).where(
            SensorReading.mission_id == mission_id
        )
    ).all()
    grid = sensor_grid(mission.area, mission.line_spacing_m, rows)
    return {
        "bounds": [list(grid.bounds[0]), list(grid.bounds[1])],
        "rows": grid.rows,
        "cols": grid.cols,
        "cell_m": list(grid.cell_m),
        "md": grid.md,
        "gpr": grid.gpr,
        "readings": grid.readings,
        "full_scale": {"md": MD_FULL_SCALE, "gpr": GPR_FULL_SCALE},
    }
