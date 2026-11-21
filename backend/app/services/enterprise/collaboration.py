"""
AutoHeal DevOps — Incident Collaboration, Ownership & Escalation Engine
Coordinates operator comments, internal notes, assignments, acknowledgements,
and severity-based unacknowledged timeout escalations with quiet hours support.
"""

from datetime import datetime, time, timezone
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Incident
from app.models.enterprise import IncidentComment, IncidentAssignment, EscalationPolicy, EscalationEvent
from app.models.user import User
from app.models.base import utc_now
from app.services.enterprise.dispatcher import NotificationDispatcher

logger = logging.getLogger(__name__)


def is_in_quiet_hours(start_str: Optional[str], end_str: Optional[str]) -> bool:
    """Checks whether the current UTC time falls within quiet hours (e.g. 22:00 to 06:00)."""
    if not start_str or not end_str:
        return False
    try:
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        start_t = time(sh, sm)
        end_t = time(eh, em)
        now_t = datetime.now(timezone.utc).time()

        if start_t <= end_t:
            return start_t <= now_t <= end_t
        else:
            # Over midnight window (e.g. 22:00 to 06:00)
            return now_t >= start_t or now_t <= end_t
    except Exception:
        return False


class IncidentCollaborationEngine:
    """
    Manages incident communication timelines, assignments, and automated escalation evaluations.
    """

    def __init__(self):
        self.dispatcher = NotificationDispatcher()

    async def add_comment(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        incident_id: str,
        content: str,
        author_name: str,
        author_role: str = "operator",
        user_id: Optional[uuid.UUID] = None,
        comment_type: str = "comment",
    ) -> IncidentComment:
        """Adds a comment, internal note, status change, or resolution summary."""
        comment = IncidentComment(
            organization_id=organization_id,
            incident_id=incident_id,
            user_id=user_id,
            author_name=author_name,
            author_role=author_role,
            comment_type=comment_type,
            content=content,
            created_at=utc_now(),
        )
        db.add(comment)
        await db.flush()
        return comment

    async def assign_incident(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        incident_id: str,
        assigned_to_name: str,
        assigned_by_name: str,
        assigned_to_user_id: Optional[uuid.UUID] = None,
        assigned_by_user_id: Optional[uuid.UUID] = None,
    ) -> IncidentAssignment:
        """Assigns an owner to an incident and creates a timeline comment."""
        # Deactivate previous active assignments
        prev_q = select(IncidentAssignment).where(
            and_(
                IncidentAssignment.organization_id == organization_id,
                IncidentAssignment.incident_id == incident_id,
                IncidentAssignment.is_active == True,
            )
        )
        prev_res = await db.execute(prev_q)
        for prev in prev_res.scalars().all():
            prev.is_active = False

        assignment = IncidentAssignment(
            organization_id=organization_id,
            incident_id=incident_id,
            assigned_to_user_id=assigned_to_user_id,
            assigned_to_name=assigned_to_name,
            assigned_by_user_id=assigned_by_user_id,
            assigned_by_name=assigned_by_name,
            assigned_at=utc_now(),
            is_active=True,
        )
        db.add(assignment)

        # Log timeline note
        await self.add_comment(
            db=db,
            organization_id=organization_id,
            incident_id=incident_id,
            content=f"Incident assigned to {assigned_to_name} by {assigned_by_name}.",
            author_name=assigned_by_name,
            author_role="operator",
            user_id=assigned_by_user_id,
            comment_type="status_change",
        )

        await db.flush()
        return assignment

    async def acknowledge_incident(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        incident_id: str,
        user_name: str,
        user_id: Optional[uuid.UUID] = None,
        note: Optional[str] = None,
    ) -> Incident:
        """Acknowledges an incident, transitioning status and halting escalation timeouts."""
        q = select(Incident).where(
            and_(
                Incident.organization_id == organization_id,
                Incident.id == incident_id,
            )
        )
        res = await db.execute(q)
        incident = res.scalars().first()
        if not incident:
            raise ValueError(f"Incident {incident_id} not found.")

        incident.status = "investigating"
        incident.recovery_status = f"Acknowledged by {user_name}"

        await self.add_comment(
            db=db,
            organization_id=organization_id,
            incident_id=incident_id,
            content=note or f"Incident acknowledged by {user_name}. Active investigation in progress.",
            author_name=user_name,
            author_role="operator",
            user_id=user_id,
            comment_type="status_change",
        )

        await db.flush()
        return incident

    async def evaluate_escalations(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
    ) -> List[EscalationEvent]:
        """
        Scans for unacknowledged incidents exceeding escalation policy timeouts.
        Advances escalation levels, logs EscalationEvents, and dispatches notifications.
        """
        # Fetch active policies for this organization
        pol_q = select(EscalationPolicy).where(
            and_(
                EscalationPolicy.organization_id == organization_id,
                EscalationPolicy.is_active == True,
            )
        )
        pol_res = await db.execute(pol_q)
        policies = pol_res.scalars().all()

        triggered_events: List[EscalationEvent] = []
        now = utc_now()

        for policy in policies:
            # Check quiet hours (unless critical incident requires alert)
            in_quiet = is_in_quiet_hours(policy.quiet_hours_start_utc, policy.quiet_hours_end_utc)
            if in_quiet and policy.quiet_hours_enabled:
                logger.info("Escalation policy '%s' currently in quiet hours window.", policy.name)

            # Look for open incidents matching policy severity
            inc_q = select(Incident).where(
                and_(
                    Incident.organization_id == organization_id,
                    Incident.status == "open",
                    Incident.severity == policy.severity,
                )
            )
            inc_res = await db.execute(inc_q)
            open_incidents = inc_res.scalars().all()

            for inc in open_incidents:
                inc_time = inc.detected_at or getattr(inc, "created_at", None) or now
                elapsed_minutes = (now - inc_time).total_seconds() / 60.0

                if elapsed_minutes < policy.unacknowledged_timeout_minutes:
                    continue

                # Check highest escalation level previously reached
                prev_esc_q = (
                    select(EscalationEvent)
                    .where(
                        and_(
                            EscalationEvent.organization_id == organization_id,
                            EscalationEvent.incident_id == inc.id,
                            EscalationEvent.policy_id == policy.id,
                        )
                    )
                    .order_by(desc(EscalationEvent.escalation_level))
                )
                prev_res = await db.execute(prev_esc_q)
                latest_esc = prev_res.scalars().first()

                current_level = latest_esc.escalation_level if latest_esc else 0
                if current_level >= policy.max_escalation_level:
                    continue

                next_level = current_level + 1
                reason = (
                    f"Incident {inc.id} unacknowledged for {int(elapsed_minutes)} minutes "
                    f"(exceeded {policy.unacknowledged_timeout_minutes}m threshold)."
                )
                action = f"Escalated to Level {next_level} under policy '{policy.name}'."

                # Dispatch notification for escalation
                await self.dispatcher.dispatch_event(
                    db=db,
                    organization_id=organization_id,
                    event_type="incident_escalated",
                    title=f"[ESCALATION L{next_level}] {inc.title}",
                    service_name=inc.service_name,
                    severity=inc.severity,
                    status=inc.status,
                    incident_id=inc.id,
                    short_evidence=reason,
                    recommended_action="Immediate operator triage required.",
                )

                event = EscalationEvent(
                    organization_id=organization_id,
                    policy_id=policy.id,
                    incident_id=inc.id,
                    escalation_level=next_level,
                    trigger_reason=reason,
                    action_taken=action,
                    notified_channels_json="[]",
                    escalated_at=utc_now(),
                )
                db.add(event)

                await self.add_comment(
                    db=db,
                    organization_id=organization_id,
                    incident_id=inc.id,
                    content=f"Incident escalated to Level {next_level}. Reason: {reason}",
                    author_name="AutoHeal Escalation Engine",
                    author_role="system",
                    comment_type="escalation",
                )

                triggered_events.append(event)

        if triggered_events:
            await db.flush()

        return triggered_events
