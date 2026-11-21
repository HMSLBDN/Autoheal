"""
AutoHeal DevOps — Enterprise Incident Lifecycle State Machine
Enforces strict transitions, policy guards, recovery verification checks,
and writes tamper-evident audit records for every state mutation.
"""

from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Dict, Optional, Set
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.incident import Incident, IncidentEvent, IncidentTransition
from app.models.recovery import RecoveryAction
from app.services.events import event_broadcaster

logger = logging.getLogger(__name__)


class IncidentLifecycleState(str, Enum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATION = "investigation"
    DIAGNOSIS = "diagnosis"
    APPROVAL_PENDING = "approval_pending"
    RECOVERY_IN_PROGRESS = "recovery_in_progress"
    RECOVERY_VERIFICATION = "recovery_verification"
    RESOLVED = "resolved"
    FAILED_RECOVERY = "failed_recovery"
    ESCALATED = "escalated"
    REOPENED = "reopened"
    # Legacy / UI aliases
    OPEN = "open"
    INVESTIGATING = "investigating"
    RECOVERING = "recovering"


# Canonical directed state transition graph
VALID_INCIDENT_TRANSITIONS: Dict[str, Set[str]] = {
    # Phase 13 full lifecycle states
    "new": {"acknowledged", "investigation", "escalated", "open", "investigating"},
    "open": {"acknowledged", "investigation", "investigating", "recovering", "recovery_in_progress", "escalated"},
    "acknowledged": {"investigation", "investigating", "diagnosis", "escalated"},
    "investigation": {"diagnosis", "approval_pending", "recovering", "recovery_in_progress", "escalated", "resolved"},
    "investigating": {"diagnosis", "approval_pending", "recovering", "recovery_in_progress", "escalated", "resolved"},
    "diagnosis": {"approval_pending", "recovery_in_progress", "recovering", "escalated", "investigation", "investigating"},
    "approval_pending": {"recovery_in_progress", "recovering", "investigation", "investigating", "escalated"},
    "recovery_in_progress": {"recovery_verification", "failed_recovery", "escalated", "resolved"},
    "recovering": {"recovery_verification", "resolved", "investigating", "investigation", "failed_recovery", "escalated"},
    "recovery_verification": {"resolved", "failed_recovery", "escalated"},
    "failed_recovery": {"escalated", "reopened", "investigation", "investigating"},
    "escalated": {"investigation", "investigating", "diagnosis", "recovery_in_progress", "resolved"},
    "resolved": {"reopened"},
    "reopened": {"investigation", "investigating", "diagnosis", "approval_pending", "escalated"},
}


class InvalidIncidentTransitionError(Exception):
    """Raised when an illegal incident lifecycle transition is attempted."""
    pass


class IncidentStateMachine:
    """
    State machine engine governing incident operational status transitions.
    """

    def is_transition_allowed(self, current_status: str, target_status: str) -> bool:
        """Checks if a transition between two states is defined in the lifecycle graph."""
        cur = current_status.lower().strip()
        tgt = target_status.lower().strip()
        allowed = VALID_INCIDENT_TRANSITIONS.get(cur, set())
        return tgt in allowed

    async def transition_incident(
        self,
        db: AsyncSession,
        incident_id: str,
        organization_id: uuid.UUID,
        target_status: str,
        actor_id: Optional[uuid.UUID],
        actor_email: str,
        actor_role: str,
        reason: str,
        evidence_id: Optional[str] = None,
        sign_off: bool = False,
    ) -> Incident:
        """
        Executes a validated incident transition with mandatory audit trail and safety checks.
        Enforces that resolution requires verified recovery or explicit operator sign-off.
        """
        stmt = (
            select(Incident)
            .options(
                selectinload(Incident.recovery_actions),
                selectinload(Incident.events),
                selectinload(Incident.transitions),
            )
            .where(
                Incident.id == incident_id,
                Incident.organization_id == organization_id,
            )
        )
        res = await db.execute(stmt)
        incident = res.scalar_one_or_none()

        if not incident:
            raise ValueError(f"Incident '{incident_id}' not found in this organization.")

        current_status = incident.status.lower().strip()
        target = target_status.lower().strip()

        # 1. State transition validation
        if not self.is_transition_allowed(current_status, target):
            raise InvalidIncidentTransitionError(
                f"Illegal incident transition from '{current_status}' to '{target}'. "
                f"Permitted next states: {sorted(list(VALID_INCIDENT_TRANSITIONS.get(current_status, set())))}."
            )

        now = datetime.now(timezone.utc)

        # 2. Strict Resolution Guard:
        # An incident cannot transition to resolved without verified recovery OR an explicit sign-off with reason
        if target == "resolved":
            has_verified_recovery = any(
                ra.verification == "passed" for ra in incident.recovery_actions
            )
            if not has_verified_recovery:
                if not sign_off or not reason or len(reason.strip()) < 8:
                    raise InvalidIncidentTransitionError(
                        "Cannot transition incident to 'resolved' without verified recovery "
                        "or an explicit operator sign-off and detailed justification (minimum 8 characters)."
                    )

        # 3. Create persistent IncidentTransition audit record
        transition_record = IncidentTransition(
            id=uuid.uuid4(),
            organization_id=organization_id,
            incident_id=incident.id,
            actor_id=actor_id,
            actor_email=actor_email,
            actor_role=actor_role,
            previous_state=current_status,
            new_state=target,
            reason=reason.strip(),
            evidence_id=evidence_id,
            sign_off=sign_off,
            created_at=now,
        )
        db.add(transition_record)

        # 4. Update Incident entity
        incident.status = target
        if target == "resolved":
            incident.resolved_at = now
            if not incident.recovery_status or incident.recovery_status == "Not started":
                incident.recovery_status = "Resolved with operator sign-off" if sign_off else "Completed / Verified healthy"
        elif target == "acknowledged":
            incident.recovery_status = "Acknowledged by operator"
        elif target == "escalated":
            incident.recovery_status = "Escalated to on-call"
        elif target == "reopened":
            incident.resolved_at = None
            incident.recovery_status = "Incident reopened for investigation"

        # 5. Add timeline event
        event_tone = "success" if target == "resolved" else ("warning" if target in ("escalated", "failed_recovery") else "neutral")
        db.add(IncidentEvent(
            incident_id=incident.id,
            label=f"Status: {target.replace('_', ' ').capitalize()}",
            detail=f"Transitioned from {current_status} to {target} by {actor_email}. Reason: {reason.strip()}",
            timestamp=now,
            tone=event_tone,
        ))

        # 6. Add security audit log
        db.add(AuditLog(
            organization_id=organization_id,
            user_id=actor_id,
            action="incident_status_transitioned",
            resource_type="incident",
            resource_id=incident.id,
            details=f"Status changed {current_status} -> {target} by '{actor_email}' ({actor_role}). Reason: {reason.strip()}",
        ))

        await db.commit()

        # 7. Broadcast SSE update for real-time frontend sync
        await event_broadcaster.broadcast(organization_id, "incident_updated", {
            "id": incident.id,
            "status": incident.status,
            "recoveryStatus": incident.recovery_status,
        })

        return incident


incident_state_machine = IncidentStateMachine()
