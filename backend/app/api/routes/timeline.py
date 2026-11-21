"""
AutoHeal DevOps — Unified Operations Timeline API Router
Provides an aggregated chronological timeline of all platform events:
Deployments, Alerts, Incidents, AI Diagnoses, Approvals, Recoveries,
Verifications, Notifications, and Escalations.
"""

from typing import Optional
from fastapi import APIRouter, Query

from app.api.deps import DatabaseDep, OrgDep
from app.schemas.enterprise import UnifiedTimelineResponse
from app.services.enterprise.timeline import UnifiedTimelineService

router = APIRouter(prefix="/timeline", tags=["Operations Timeline"])
timeline_service = UnifiedTimelineService()


@router.get("", response_model=UnifiedTimelineResponse, summary="Get unified operations timeline")
async def get_operations_timeline(
    org: OrgDep,
    db: DatabaseDep,
    service_id: Optional[str] = Query(None, alias="serviceId"),
    limit: int = Query(default=50, le=200),
) -> UnifiedTimelineResponse:
    """Retrieves an aggregated, chronologically sorted timeline across all operational event streams."""
    return await timeline_service.get_timeline(
        db=db,
        organization_id=org.id,
        service_id=service_id,
        limit=limit,
    )
