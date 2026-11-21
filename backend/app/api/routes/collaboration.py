"""
AutoHeal DevOps — Incident Collaboration & Workflow API Router
Provides incident communication timeline, ownership assignment, acknowledgment,
and manual escalation.
"""

from datetime import datetime
from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, and_, desc

from app.api.deps import DatabaseDep, OrgDep, RequireRole, UserDep
from app.models.incident import Incident
from app.models.enterprise import IncidentComment, IncidentAssignment, EscalationEvent
from app.schemas.enterprise import (
    IncidentCommentCreate,
    IncidentCommentResponse,
    IncidentAssignmentRequest,
    IncidentAssignmentResponse,
    IncidentAcknowledgeRequest,
    IncidentEscalateRequest,
    EscalationEventResponse,
)
from app.services.enterprise.collaboration import IncidentCollaborationEngine

router = APIRouter(prefix="/incidents", tags=["Incident Collaboration"])
collab_engine = IncidentCollaborationEngine()


def serialize_comment(c: IncidentComment) -> IncidentCommentResponse:
    return IncidentCommentResponse(
        id=str(c.id),
        incident_id=c.incident_id,
        author_name=c.author_name,
        author_role=c.author_role,
        comment_type=c.comment_type,
        content=c.content,
        created_at=c.created_at.isoformat() if c.created_at else "",
    )


def serialize_assignment(a: IncidentAssignment) -> IncidentAssignmentResponse:
    return IncidentAssignmentResponse(
        id=str(a.id),
        incident_id=a.incident_id,
        assigned_to_name=a.assigned_to_name,
        assigned_by_name=a.assigned_by_name,
        assigned_at=a.assigned_at.isoformat() if a.assigned_at else "",
        is_active=a.is_active,
    )


@router.get("/{incident_id}/comments", response_model=List[IncidentCommentResponse], summary="List incident communication timeline")
async def list_incident_comments(
    incident_id: str,
    org: OrgDep,
    db: DatabaseDep,
) -> List[IncidentCommentResponse]:
    """Retrieves comments, internal notes, status transitions, and resolution summaries for an incident."""
    # Validate incident belongs to tenant
    inc_q = select(Incident).where(
        and_(
            Incident.organization_id == org.id,
            Incident.id == incident_id,
        )
    )
    inc_res = await db.execute(inc_q)
    if not inc_res.scalars().first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found.")

    q = (
        select(IncidentComment)
        .where(
            and_(
                IncidentComment.organization_id == org.id,
                IncidentComment.incident_id == incident_id,
            )
        )
        .order_by(IncidentComment.created_at.asc())
    )
    res = await db.execute(q)
    return [serialize_comment(c) for c in res.scalars().all()]


@router.post("/{incident_id}/comments", response_model=IncidentCommentResponse, summary="Post comment or note", status_code=status.HTTP_201_CREATED)
async def create_incident_comment(
    incident_id: str,
    payload: IncidentCommentCreate,
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
) -> IncidentCommentResponse:
    """Adds a timeline comment or internal note. Operator or Admin role required."""
    if user.role not in ["operator", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operator or Admin role required.")

    # Validate incident
    inc_q = select(Incident).where(
        and_(
            Incident.organization_id == org.id,
            Incident.id == incident_id,
        )
    )
    inc_res = await db.execute(inc_q)
    if not inc_res.scalars().first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found.")

    user_name = user.full_name or user.email
    comment = await collab_engine.add_comment(
        db=db,
        organization_id=org.id,
        incident_id=incident_id,
        content=payload.content,
        author_name=user_name,
        author_role=user.role,
        user_id=user.id,
        comment_type=payload.comment_type,
    )
    return serialize_comment(comment)


@router.get("/{incident_id}/assignment", response_model=Optional[IncidentAssignmentResponse], summary="Get active incident assignment")
async def get_incident_assignment(
    incident_id: str,
    org: OrgDep,
    db: DatabaseDep,
) -> Optional[IncidentAssignmentResponse]:
    """Retrieves current owner assignment for the incident."""
    q = select(IncidentAssignment).where(
        and_(
            IncidentAssignment.organization_id == org.id,
            IncidentAssignment.incident_id == incident_id,
            IncidentAssignment.is_active == True,
        )
    )
    res = await db.execute(q)
    assignment = res.scalars().first()
    return serialize_assignment(assignment) if assignment else None


@router.post("/{incident_id}/assign", response_model=IncidentAssignmentResponse, summary="Assign incident ownership")
async def assign_incident_owner(
    incident_id: str,
    payload: IncidentAssignmentRequest,
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
) -> IncidentAssignmentResponse:
    """Assigns an incident owner. Operator or Admin role required."""
    if user.role not in ["operator", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operator or Admin role required.")

    # Validate incident
    inc_q = select(Incident).where(
        and_(
            Incident.organization_id == org.id,
            Incident.id == incident_id,
        )
    )
    inc_res = await db.execute(inc_q)
    if not inc_res.scalars().first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found.")

    assigned_to_uuid = None
    if payload.assigned_to_user_id:
        try:
            assigned_to_uuid = uuid.UUID(payload.assigned_to_user_id)
        except ValueError:
            pass

    user_name = user.full_name or user.email
    assignment = await collab_engine.assign_incident(
        db=db,
        organization_id=org.id,
        incident_id=incident_id,
        assigned_to_name=payload.assigned_to_name,
        assigned_by_name=user_name,
        assigned_to_user_id=assigned_to_uuid,
        assigned_by_user_id=user.id,
    )
    return serialize_assignment(assignment)


@router.post("/{incident_id}/acknowledge", summary="Acknowledge incident")
async def acknowledge_incident_route(
    incident_id: str,
    payload: IncidentAcknowledgeRequest,
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
):
    """Acknowledges an incident, transitions status to investigating, and silences timeout escalations."""
    if user.role not in ["operator", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operator or Admin role required.")

    user_name = user.full_name or user.email
    try:
        incident = await collab_engine.acknowledge_incident(
            db=db,
            organization_id=org.id,
            incident_id=incident_id,
            user_name=user_name,
            user_id=user.id,
            note=payload.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return {
        "status": "acknowledged",
        "incident_id": incident.id,
        "incident_status": incident.status,
        "acknowledged_by": user_name,
    }


@router.post("/{incident_id}/escalate", response_model=EscalationEventResponse, summary="Manually escalate incident")
async def manual_escalate_route(
    incident_id: str,
    payload: IncidentEscalateRequest,
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
) -> EscalationEventResponse:
    """Manually triggers an escalation for an incident."""
    if user.role not in ["operator", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operator or Admin role required.")

    # Validate incident
    inc_q = select(Incident).where(
        and_(
            Incident.organization_id == org.id,
            Incident.id == incident_id,
        )
    )
    inc_res = await db.execute(inc_q)
    incident = inc_res.scalars().first()
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found.")

    user_name = user.full_name or user.email
    target_level = payload.target_level or 1

    event = EscalationEvent(
        organization_id=org.id,
        policy_id=uuid.uuid4(),  # Manual escalation policy pseudo-ID
        incident_id=incident_id,
        escalation_level=target_level,
        trigger_reason=payload.reason,
        action_taken=f"Manually escalated to Level {target_level} by {user_name}.",
        notified_channels_json="[]",
    )
    db.add(event)

    await collab_engine.add_comment(
        db=db,
        organization_id=org.id,
        incident_id=incident_id,
        content=f"Incident manually escalated to Level {target_level} by {user_name}. Reason: {payload.reason}",
        author_name=user_name,
        author_role=user.role,
        user_id=user.id,
        comment_type="escalation",
    )

    await db.flush()

    return EscalationEventResponse(
        id=str(event.id),
        policy_id=str(event.policy_id),
        incident_id=event.incident_id,
        escalation_level=event.escalation_level,
        trigger_reason=event.trigger_reason,
        action_taken=event.action_taken,
        notified_channels=[],
        escalated_at=event.escalated_at.isoformat() if event.escalated_at else "",
    )
