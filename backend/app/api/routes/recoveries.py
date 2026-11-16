"""
AutoHeal DevOps — Recovery Actions & Policy Approval Router
"""

from datetime import datetime, timezone
from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from app.api.deps import DatabaseDep, OrgDep, RequireOperatorDep
from app.models.audit import AuditLog
from app.models.incident import Incident
from app.models.recovery import RecoveryAction, RecoveryResult
from app.schemas.recovery import (
    RecoveryActionResponse,
    RecoveryRejectRequest,
    RecoveryResultResponse,
)
from app.services.events import event_broadcaster
from app.services.recovery.executor import RecoveryExecutor

router = APIRouter(prefix="/recoveries", tags=["Recoveries"])


def format_recovery_response(rec: RecoveryAction) -> RecoveryActionResponse:
    """Formats RecoveryAction DB model into schema matching frontend RecoveryAction interface."""
    result_data: Optional[RecoveryResultResponse] = None
    if rec.result:
        result_data = RecoveryResultResponse(
            verified=rec.result.verified,
            summary=rec.result.summary,
            completed_at=rec.result.completed_at.strftime("%Y-%m-%d %H:%M UTC"),
        )

    # Format human-friendly requested_at string for frontend
    requested_at_str = rec.requested_at.strftime("%Y-%m-%d %H:%M UTC")

    return RecoveryActionResponse(
        id=rec.id,
        incident_id=rec.incident_id,
        service_name=rec.service_name,
        action=rec.action,
        status=rec.status,  # type: ignore[arg-type]
        approval_required=rec.approval_required,
        requested_by=rec.requested_by,
        requested_at=requested_at_str,
        duration_seconds=rec.duration_seconds,
        verification=rec.verification,  # type: ignore[arg-type]
        result=result_data,
    )


@router.get(
    "",
    response_model=List[RecoveryActionResponse],
    summary="List organization recovery actions",
)
async def list_recoveries(
    org: OrgDep,
    db: DatabaseDep,
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> List[RecoveryActionResponse]:
    """
    Returns recovery action queue and recorded operation history.
    Directly satisfies recoveriesApi.list() in lib/api/resources.ts.
    """
    stmt = (
        select(RecoveryAction)
        .join(Incident, RecoveryAction.incident_id == Incident.id)
        .options(selectinload(RecoveryAction.result))
        .where(Incident.organization_id == org.id)
    )

    if status_filter and status_filter.lower() != "all":
        stmt = stmt.where(RecoveryAction.status == status_filter.lower())

    stmt = stmt.order_by(desc(RecoveryAction.requested_at)).offset(skip).limit(limit)
    result = await db.execute(stmt)
    actions = result.scalars().all()

    return [format_recovery_response(a) for a in actions]


@router.post(
    "/{recovery_id}/approve",
    response_model=RecoveryActionResponse,
    summary="Approve policy-gated recovery action",
)
async def approve_recovery(
    recovery_id: str,
    org: OrgDep,
    current_user: RequireOperatorDep,
    db: DatabaseDep,
) -> RecoveryActionResponse:
    """
    Submits human-in-the-loop approval for a pending recovery action.
    Validates state transitions and updates action status transactionally.
    Directly satisfies recoveriesApi.approve(id) in lib/api/resources.ts.
    """
    stmt = (
        select(RecoveryAction)
        .join(Incident, RecoveryAction.incident_id == Incident.id)
        .options(selectinload(RecoveryAction.result))
        .where(
            RecoveryAction.id == recovery_id,
            Incident.organization_id == org.id,
        )
    )
    result = await db.execute(stmt)
    recovery = result.scalar_one_or_none()

    if not recovery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recovery action '{recovery_id}' was not found in this organization.",
        )

    # State transition validation
    if recovery.status != "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Recovery action '{recovery_id}' cannot be approved because current status is '{recovery.status}'.",
        )

    # Update recovery status to approved
    recovery.status = "approved"
    recovery.approver_id = current_user.id

    # Transactionally update associated incident
    inc_res = await db.execute(select(Incident).where(Incident.id == recovery.incident_id))
    incident = inc_res.scalar_one_or_none()
    if incident:
        incident.recovery_status = "Approved / Awaiting execution"

    # Add audit log
    db.add(AuditLog(
        organization_id=org.id,
        user_id=current_user.id,
        action="recovery_approved",
        resource_type="recovery_action",
        resource_id=recovery.id,
        details=f"Operator '{current_user.email}' approved recovery action '{recovery.id}' for service '{recovery.service_name}'.",
    ))

    await db.flush()

    resp = format_recovery_response(recovery)
    await event_broadcaster.broadcast(org.id, "recovery_updated", resp.model_dump())
    if incident:
        await event_broadcaster.broadcast(org.id, "incident_updated", {
            "id": incident.id,
            "recoveryStatus": incident.recovery_status,
        })

    return resp


@router.post(
    "/{recovery_id}/reject",
    response_model=RecoveryActionResponse,
    summary="Reject pending recovery action",
)
async def reject_recovery(
    recovery_id: str,
    org: OrgDep,
    current_user: RequireOperatorDep,
    db: DatabaseDep,
    payload: Optional[RecoveryRejectRequest] = None,
) -> RecoveryActionResponse:
    """
    Rejects a pending recovery action, setting status strictly to 'rejected' (not failed).
    Attaches diagnostic summary and logs the rejection in audit logs.
    """
    stmt = (
        select(RecoveryAction)
        .join(Incident, RecoveryAction.incident_id == Incident.id)
        .options(selectinload(RecoveryAction.result))
        .where(
            RecoveryAction.id == recovery_id,
            Incident.organization_id == org.id,
        )
    )
    result = await db.execute(stmt)
    recovery = result.scalar_one_or_none()

    if not recovery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recovery action '{recovery_id}' was not found in this organization.",
        )

    # State transition validation
    if recovery.status in ["completed", "rejected", "failed"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Recovery action '{recovery_id}' cannot be rejected because current status is '{recovery.status}'.",
        )

    # Set status strictly to 'rejected'
    recovery.status = "rejected"
    recovery.verification = "failed"

    rejection_reason = payload.reason if payload and payload.reason else "Operator rejected recovery action"

    # Attach diagnostic rejection result
    if recovery.result:
        recovery.result.verified = False
        recovery.result.summary = rejection_reason
        recovery.result.completed_at = datetime.now(timezone.utc)
    else:
        recovery.result = RecoveryResult(
            id=uuid.uuid4(),
            recovery_action_id=recovery.id,
            verified=False,
            summary=rejection_reason,
            completed_at=datetime.now(timezone.utc),
        )

    # Update associated incident
    inc_res = await db.execute(select(Incident).where(Incident.id == recovery.incident_id))
    incident = inc_res.scalar_one_or_none()
    if incident:
        incident.recovery_status = "Action rejected"
        incident.status = "investigating"

    # Add audit log
    db.add(AuditLog(
        organization_id=org.id,
        user_id=current_user.id,
        action="recovery_rejected",
        resource_type="recovery_action",
        resource_id=recovery.id,
        details=f"Operator '{current_user.email}' rejected action '{recovery.id}'. Reason: {rejection_reason}",
    ))

    await db.flush()

    resp = format_recovery_response(recovery)
    await event_broadcaster.broadcast(org.id, "recovery_updated", resp.model_dump())
    if incident:
        await event_broadcaster.broadcast(org.id, "incident_updated", {
            "id": incident.id,
            "recoveryStatus": incident.recovery_status,
        })

    return resp


@router.post(
    "/{recovery_id}/execute",
    response_model=RecoveryActionResponse,
    summary="Execute approved recovery action and verify health",
)
async def execute_recovery_endpoint(
    recovery_id: str,
    org: OrgDep,
    current_user: RequireOperatorDep,
    db: DatabaseDep,
) -> RecoveryActionResponse:
    """
    Triggers controlled execution of an approved recovery action.
    Runs simulated remediation steps and coordinates post-recovery health verification.
    """
    stmt = (
        select(RecoveryAction)
        .join(Incident, RecoveryAction.incident_id == Incident.id)
        .where(
            RecoveryAction.id == recovery_id,
            Incident.organization_id == org.id,
        )
    )
    result = await db.execute(stmt)
    recovery = result.scalar_one_or_none()
    if not recovery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recovery action '{recovery_id}' was not found in this organization.",
        )

    try:
        executor = RecoveryExecutor()
        executed_recovery = await executor.execute_recovery(db, recovery_id=recovery.id)
        resp = format_recovery_response(executed_recovery)
        await event_broadcaster.broadcast(org.id, "recovery_updated", resp.model_dump())
        return resp
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )
