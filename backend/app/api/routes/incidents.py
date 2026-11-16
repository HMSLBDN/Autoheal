"""
AutoHeal DevOps — Incidents, Evidence & PDF Reports Router
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from app.api.deps import DatabaseDep, OrgDep, RequireOperatorDep
from app.models.audit import AuditLog
from app.models.incident import Incident
from app.models.recovery import RecoveryAction
from app.schemas.incident import (
    IncidentEvidenceResponse,
    IncidentEventResponse,
    IncidentResponse,
)
from app.schemas.recovery import RecoveryActionResponse
from app.services.pdf_report import generate_incident_pdf

router = APIRouter(prefix="/incidents", tags=["Incidents"])


def format_incident_response(inc: Incident) -> IncidentResponse:
    """Formats Incident DB model into schema matching frontend Incident interface."""
    return IncidentResponse(
        id=inc.id,
        service_id=inc.service_id,
        service_name=inc.service_name,
        title=inc.title,
        severity=inc.severity,  # type: ignore[arg-type]
        status=inc.status,  # type: ignore[arg-type]
        detected_at=inc.detected_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        recovery_status=inc.recovery_status,
        error_rate=inc.error_rate,
        threshold=inc.threshold,
        probable_cause=inc.probable_cause,
        recommended_action=inc.recommended_action,
        evidence=[
            IncidentEvidenceResponse(
                id=ev.id,
                kind=ev.kind,  # type: ignore[arg-type]
                title=ev.title,
                detail=ev.detail,
                timestamp=ev.timestamp.strftime("%H:%M:%S"),
            )
            for ev in inc.evidence
        ],
        events=[
            IncidentEventResponse(
                id=event.id,
                label=event.label,
                detail=event.detail,
                timestamp=event.timestamp.strftime("%H:%M:%S"),
                tone=event.tone,  # type: ignore[arg-type]
            )
            for event in inc.events
        ],
    )


@router.get(
    "",
    response_model=List[IncidentResponse],
    summary="List organization incidents",
)
async def list_incidents(
    org: OrgDep,
    db: DatabaseDep,
    severity: Optional[str] = Query(None, description="Filter by severity (critical, high, medium, low)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (open, investigating, recovering, resolved)"),
    service_id: Optional[str] = Query(None, description="Filter by service ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> List[IncidentResponse]:
    """
    Returns organization incidents with correlated evidence and events.
    Directly satisfies incidentsApi.list() in lib/api/resources.ts.
    """
    stmt = (
        select(Incident)
        .options(selectinload(Incident.evidence), selectinload(Incident.events))
        .where(Incident.organization_id == org.id)
    )

    if severity and severity.lower() != "all":
        stmt = stmt.where(Incident.severity == severity.lower())
    if status_filter and status_filter.lower() != "all":
        stmt = stmt.where(Incident.status == status_filter.lower())
    if service_id and service_id.lower() != "all":
        stmt = stmt.where(Incident.service_id == service_id)

    stmt = stmt.order_by(desc(Incident.detected_at)).offset(skip).limit(limit)
    result = await db.execute(stmt)
    incidents = result.scalars().all()

    return [format_incident_response(i) for i in incidents]


@router.get(
    "/{incident_id}",
    response_model=IncidentResponse,
    summary="Get incident details",
)
async def get_incident(
    incident_id: str,
    org: OrgDep,
    db: DatabaseDep,
) -> IncidentResponse:
    """
    Returns single incident with attached evidence and event timeline.
    Directly satisfies incidentsApi.get(id) in lib/api/resources.ts.
    """
    stmt = (
        select(Incident)
        .options(selectinload(Incident.evidence), selectinload(Incident.events))
        .where(
            Incident.id == incident_id,
            Incident.organization_id == org.id,
        )
    )
    result = await db.execute(stmt)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' was not found in this organization.",
        )

    return format_incident_response(incident)


@router.post(
    "/{incident_id}/recover",
    response_model=RecoveryActionResponse,
    summary="Request controlled incident recovery",
    status_code=status.HTTP_200_OK,
)
async def request_recovery(
    incident_id: str,
    org: OrgDep,
    current_user: RequireOperatorDep,
    db: DatabaseDep,
) -> RecoveryActionResponse:
    """
    Submits a controlled recovery request for an active incident.
    Validates state transitions and enqueues action for operator review.
    Directly satisfies incidentsApi.requestRecovery(id) in lib/api/resources.ts.
    """
    stmt = (
        select(Incident)
        .where(
            Incident.id == incident_id,
            Incident.organization_id == org.id,
        )
    )
    result = await db.execute(stmt)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' was not found in this organization.",
        )

    if incident.status == "resolved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Incident '{incident_id}' is already resolved. No recovery action needed.",
        )

    # Check for active existing recovery in flight
    existing_rec_res = await db.execute(
        select(RecoveryAction).where(
            RecoveryAction.incident_id == incident.id,
            RecoveryAction.status.in_(["pending_approval", "approved", "running"]),
        )
    )
    active_recovery = existing_rec_res.scalar_one_or_none()
    if active_recovery:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Recovery action '{active_recovery.id}' is already active for this incident (status: {active_recovery.status}).",
        )

    # Generate next recovery ID
    rec_count_res = await db.execute(select(RecoveryAction))
    count = len(rec_count_res.scalars().all()) + 700
    recovery_id = f"REC-{count}"

    action_name = incident.recommended_action or "Rollback to previous stable release"

    recovery = RecoveryAction(
        id=recovery_id,
        incident_id=incident.id,
        service_id=incident.service_id,
        service_name=incident.service_name,
        action=action_name,
        status="pending_approval",
        approval_required=True,
        requested_by=current_user.email,
        requested_at=datetime.now(timezone.utc),
        verification="pending",
    )
    db.add(recovery)

    # Update incident status
    incident.status = "recovering"
    incident.recovery_status = "Approval required"

    # Audit log entry
    db.add(AuditLog(
        organization_id=org.id,
        user_id=current_user.id,
        action="recovery_requested",
        resource_type="incident",
        resource_id=incident.id,
        details=f"Operator '{current_user.email}' requested recovery action '{recovery.id}' with operation '{action_name}'.",
    ))

    await db.flush()

    return RecoveryActionResponse(
        id=recovery.id,
        incident_id=recovery.incident_id,
        service_name=recovery.service_name,
        action=recovery.action,
        status=recovery.status,  # type: ignore[arg-type]
        approval_required=recovery.approval_required,
        requested_by=recovery.requested_by,
        requested_at=recovery.requested_at.strftime("%H:%M:%S"),
        duration_seconds=recovery.duration_seconds,
        verification=recovery.verification,  # type: ignore[arg-type]
        result=None,
    )


@router.get(
    "/{incident_id}/report",
    summary="Download incident post-mortem PDF report",
)
async def download_incident_report(
    incident_id: str,
    org: OrgDep,
    db: DatabaseDep,
) -> Response:
    """
    Generates and streams a real ReportLab PDF post-mortem document.
    Directly satisfies incidentsApi.downloadReport(id) in lib/api/resources.ts.
    """
    stmt = (
        select(Incident)
        .options(
            selectinload(Incident.evidence),
            selectinload(Incident.events),
            selectinload(Incident.recovery_actions),
        )
        .where(
            Incident.id == incident_id,
            Incident.organization_id == org.id,
        )
    )
    result = await db.execute(stmt)
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' was not found in this organization.",
        )

    pdf_bytes = generate_incident_pdf(incident)

    filename = f"{incident.id}-report.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )
