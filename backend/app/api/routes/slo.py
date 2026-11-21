"""
AutoHeal DevOps — SLO & Operational Metrics Router
Exposes operational reliability scorecard and real SLA performance metrics for pilot teams.
"""

from typing import List, Optional
from fastapi import APIRouter, Query

from app.api.deps import DatabaseDep, OrgDep
from app.schemas.slo import SLOMetricItem, SLOSummaryResponse
from app.services.slo.calculator import slo_calculator

router = APIRouter(prefix="/slo", tags=["SLO & Operational Metrics"])


@router.get(
    "/summary",
    response_model=SLOSummaryResponse,
    summary="Get organization SLO performance scorecard",
)
async def get_slo_summary(
    org: OrgDep,
    db: DatabaseDep,
    period: str = Query("last_24h", description="Evaluation window: last_24h, last_7d, last_30d"),
) -> SLOSummaryResponse:
    """
    Returns real operational SLO metrics including MTTA, MTTR, availability,
    recovery verification rates, and notification reliability with provenance tags.
    """
    return await slo_calculator.get_slo_summary(db=db, organization_id=org.id, period=period)


@router.get(
    "/metrics",
    response_model=List[SLOMetricItem],
    summary="List individual operational SLO metrics",
)
async def list_slo_metrics(
    org: OrgDep,
    db: DatabaseDep,
    period: str = Query("last_24h", description="Evaluation window: last_24h, last_7d, last_30d"),
) -> List[SLOMetricItem]:
    """
    Returns breakdown of individual service level metrics.
    """
    summary = await slo_calculator.get_slo_summary(db=db, organization_id=org.id, period=period)
    return summary.metrics
