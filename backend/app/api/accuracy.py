"""The detector's expected accuracy for survey settings (app/detection/accuracy.py), for the planning form and the
Sensors page. Simulated data: it compares settings inside the simulation and does not predict field performance."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query, status

from app.detection.accuracy import ALTITUDES_M, SPACINGS_M, SPEEDS_MPS, estimate
from app.schemas import AccuracyEstimate, SoilType

from .deps import CurrentUser

router = APIRouter(prefix="/api/accuracy", tags=["accuracy"])
NO_TABLE = "No accuracy table: run python -m scripts.accuracy_table in backend/"


def accuracy_read(soil_type: str, altitude_m: float, speed_mps: float, spacing_m: float) -> AccuracyEstimate | None:
    e = estimate(soil_type, altitude_m, speed_mps, spacing_m)
    return None if e is None else AccuracyEstimate(**asdict(e))


@router.get("", response_model=AccuracyEstimate)
def get_accuracy(
    _: CurrentUser,
    soil_type: SoilType = "dry_sand",
    altitude_m: float = Query(1.5, ge=0.5, le=5.0),
    speed_mps: float = Query(2.0, ge=0.5, le=5.0),
    line_spacing_m: float = Query(2.0, ge=0.5, le=5.0),
) -> AccuracyEstimate:
    e = accuracy_read(soil_type, altitude_m, speed_mps, line_spacing_m)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_TABLE)
    return e


@router.get("/grid", response_model=list[AccuracyEstimate])
def get_accuracy_grid(_: CurrentUser, soil_type: SoilType = "dry_sand") -> list[AccuracyEstimate]:
    """Every grid point of one soil, for the Sensors page's chart."""
    rows = [accuracy_read(soil_type, a, s, d) for a in ALTITUDES_M for s in SPEEDS_MPS for d in SPACINGS_M]
    if any(r is None for r in rows):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_TABLE)
    return rows
