"""
AutoHeal DevOps — Escalation Policies API Router
Manages automated unacknowledged incident timeout escalation rules, multi-level alerting,
and quiet hours suppression.
"""

from datetime import datetime
import json
from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, and_, desc

from app.api.deps import DatabaseDep, OrgDep, RequireRole, UserDep
from app.models.enterprise import EscalationPolicy, EscalationEvent
from app.schemas.enterprise import (
    EscalationPolicyCreate,
    EscalationPolicyResponse,
    EscalationPolicyUpdate,
    EscalationEventResponse,
    EscalationLevelRule,
)
from app.services.enterprise.collaboration import IncidentCollaborationEngine

router = APIRouter(prefix="/escalations", tags=["Escalations"])
collab_engine = IncidentCollaborationEngine()


def serialize_policy(p: EscalationPolicy) -> EscalationPolicyResponse:
    try:
        raw_rules = json.loads(p.rules_json or "[]")
        rules = [
            EscalationLevelRule(
                level=r.get("level", idx + 1),
                timeout_minutes=r.get("timeout_minutes", 15),
                channel_ids=r.get("channel_ids", []),
                target_roles=r.get("target_roles", []),
            )
            for idx, r in enumerate(raw_rules)
        ]
    except Exception:
        rules = []

    return EscalationPolicyResponse(
        id=str(p.id),
        organization_id=str(p.organization_id),
        name=p.name,
        severity=p.severity,
        unacknowledged_timeout_minutes=p.unacknowledged_timeout_minutes,
        max_escalation_level=p.max_escalation_level,
        rules=rules,
        quiet_hours_enabled=p.quiet_hours_enabled,
        quiet_hours_start_utc=p.quiet_hours_start_utc,
        quiet_hours_end_utc=p.quiet_hours_end_utc,
        is_active=p.is_active,
        created_at=p.created_at.isoformat() if p.created_at else "",
    )


def serialize_escalation_event(e: EscalationEvent) -> EscalationEventResponse:
    try:
        channels = json.loads(e.notified_channels_json or "[]")
    except Exception:
        channels = []

    return EscalationEventResponse(
        id=str(e.id),
        policy_id=str(e.policy_id),
        incident_id=e.incident_id,
        escalation_level=e.escalation_level,
        trigger_reason=e.trigger_reason,
        action_taken=e.action_taken,
        notified_channels=channels,
        escalated_at=e.escalated_at.isoformat() if e.escalated_at else "",
    )


@router.get("/policies", response_model=List[EscalationPolicyResponse], summary="List escalation policies")
async def list_policies(
    org: OrgDep,
    db: DatabaseDep,
) -> List[EscalationPolicyResponse]:
    """Lists escalation policies configured for the organization."""
    q = select(EscalationPolicy).where(
        EscalationPolicy.organization_id == org.id
    ).order_by(desc(EscalationPolicy.created_at))
    res = await db.execute(q)
    return [serialize_policy(p) for p in res.scalars().all()]


@router.post("/policies", response_model=EscalationPolicyResponse, summary="Create escalation policy", status_code=status.HTTP_201_CREATED)
async def create_policy(
    payload: EscalationPolicyCreate,
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
) -> EscalationPolicyResponse:
    """Creates a new escalation policy. Admin role required."""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required to configure escalation policies.")

    rules_dict = [r.model_dump() for r in payload.rules]
    policy = EscalationPolicy(
        organization_id=org.id,
        name=payload.name,
        severity=payload.severity,
        unacknowledged_timeout_minutes=payload.unacknowledged_timeout_minutes,
        max_escalation_level=payload.max_escalation_level,
        rules_json=json.dumps(rules_dict),
        quiet_hours_enabled=payload.quiet_hours_enabled,
        quiet_hours_start_utc=payload.quiet_hours_start_utc,
        quiet_hours_end_utc=payload.quiet_hours_end_utc,
        is_active=payload.is_active,
    )
    db.add(policy)
    await db.flush()
    return serialize_policy(policy)


@router.get("/policies/{policy_id}", response_model=EscalationPolicyResponse, summary="Get escalation policy")
async def get_policy(
    policy_id: str,
    org: OrgDep,
    db: DatabaseDep,
) -> EscalationPolicyResponse:
    """Retrieves policy definition."""
    try:
        pid = uuid.UUID(policy_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid policy ID.")

    q = select(EscalationPolicy).where(
        and_(
            EscalationPolicy.organization_id == org.id,
            EscalationPolicy.id == pid,
        )
    )
    res = await db.execute(q)
    policy = res.scalars().first()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escalation policy not found.")

    return serialize_policy(policy)


@router.patch("/policies/{policy_id}", response_model=EscalationPolicyResponse, summary="Update escalation policy")
async def update_policy(
    policy_id: str,
    payload: EscalationPolicyUpdate,
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
) -> EscalationPolicyResponse:
    """Updates escalation policy. Admin role required."""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required to update escalation policies.")

    try:
        pid = uuid.UUID(policy_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid policy ID.")

    q = select(EscalationPolicy).where(
        and_(
            EscalationPolicy.organization_id == org.id,
            EscalationPolicy.id == pid,
        )
    )
    res = await db.execute(q)
    policy = res.scalars().first()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escalation policy not found.")

    if payload.name is not None:
        policy.name = payload.name
    if payload.severity is not None:
        policy.severity = payload.severity
    if payload.unacknowledged_timeout_minutes is not None:
        policy.unacknowledged_timeout_minutes = payload.unacknowledged_timeout_minutes
    if payload.max_escalation_level is not None:
        policy.max_escalation_level = payload.max_escalation_level
    if payload.rules is not None:
        policy.rules_json = json.dumps([r.model_dump() for r in payload.rules])
    if payload.quiet_hours_enabled is not None:
        policy.quiet_hours_enabled = payload.quiet_hours_enabled
    if payload.quiet_hours_start_utc is not None:
        policy.quiet_hours_start_utc = payload.quiet_hours_start_utc
    if payload.quiet_hours_end_utc is not None:
        policy.quiet_hours_end_utc = payload.quiet_hours_end_utc
    if payload.is_active is not None:
        policy.is_active = payload.is_active

    await db.flush()
    return serialize_policy(policy)


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete escalation policy")
async def delete_policy(
    policy_id: str,
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
):
    """Deletes escalation policy. Admin role required."""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required to delete escalation policies.")

    try:
        pid = uuid.UUID(policy_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid policy ID.")

    q = select(EscalationPolicy).where(
        and_(
            EscalationPolicy.organization_id == org.id,
            EscalationPolicy.id == pid,
        )
    )
    res = await db.execute(q)
    policy = res.scalars().first()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escalation policy not found.")

    await db.delete(policy)
    await db.flush()


@router.post("/evaluate", response_model=List[EscalationEventResponse], summary="Trigger escalation policy evaluation")
async def trigger_evaluation(
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
) -> List[EscalationEventResponse]:
    """Evaluates unacknowledged incident timeouts and triggers escalations. Operator or Admin role."""
    if user.role not in ["operator", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operator or Admin role required.")

    events = await collab_engine.evaluate_escalations(db=db, organization_id=org.id)
    return [serialize_escalation_event(e) for e in events]


@router.get("/events", response_model=List[EscalationEventResponse], summary="List historical escalation events")
async def list_escalation_events(
    org: OrgDep,
    db: DatabaseDep,
    incident_id: Optional[str] = None,
    limit: int = Query(default=50, le=200),
) -> List[EscalationEventResponse]:
    """Lists past escalation events."""
    q = select(EscalationEvent).where(EscalationEvent.organization_id == org.id)
    if incident_id:
        q = q.where(EscalationEvent.incident_id == incident_id)

    q = q.order_by(desc(EscalationEvent.escalated_at)).limit(limit)
    res = await db.execute(q)
    return [serialize_escalation_event(e) for e in res.scalars().all()]
