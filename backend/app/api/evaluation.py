from __future__ import annotations

from fastapi import APIRouter

from app.evaluation.report import evaluation_report

from .deps import CurrentUser

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


@router.get("")
def get_evaluation(_: CurrentUser) -> dict:
    """Baseline vs. adaptive on the evaluation seeds (simulated data). The first call takes a few seconds."""
    return evaluation_report()
