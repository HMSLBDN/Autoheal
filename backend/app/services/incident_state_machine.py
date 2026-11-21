"""
AutoHeal DevOps — Incident Lifecycle State Machine & Resolution Integrity Engine
Enforces verifiable health gates for incident resolution, distinct manual sign-off tracking,
auditable lifecycle transitions, and regression safety against unauthorized resolution bypasses.
"""

from datetime import datetime, timezone
from enum import Enum
import json
import logging
from typing import Dict, List, Optional, Set, Tuple
import uuid

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.incident import Incident, IncidentEvent, IncidentTransition
from app.models.recovery import RecoveryAction, RecoveryResult
from app.models.user import User
from app.services.events import event_broadcaster

logger = logging.getLogger(__name__)


class IncidentState(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RECOVERING = "recovering"
    ESCALATED = "escalated"
    RESOLVED = "resolved"


# Valid state transitions graph
VALID_INCIDENT_TRANSITIONS: Dict[str, Set[str]] = {
    "open": {"investigating", "recovering", "escalated", "resolved"},
    "investigating": {"recovering", "escalated", "resolved"},
    "recovering": {"investigating", "escalated", "resolved"},
    "escalated": {"investigating", "recovering", "resolved"},
    "resolved": {"open", "investigating"},  # Allows reopening on regression or re-firing alert
}


class IncidentResolutionIntegrityError(HTTPException):
    """Raised when an incident resolution violates verification or manual sign-off rules."""
    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)


class IncidentStateMachine:
    """
    Manages incident lifecycle transitions with strict verification integrity:
    1. Incident cannot be marked resolved simply because a recovery command executed.
    2. Successful recovery requires a successful health verification (verification='passed').
    3. Failed verification keeps the incident unresolved.
    4. Failed recovery can be escalated.
    5. Manual sign-off is separately recorded and cannot falsely claim recovery succeeded.
    6. Every transition has an auditable actor, timestamp, previous state, new state, and reason.
    """

    @staticmethod
    def is_valid_transition(current_status: str, target_status: str) -> bool:
        cur = current_status.lower().strip()
        tgt = target_status.lower().strip()
        if cur == tgt:
            return False
        return tgt in VALID_INCIDENT_TRANSITIONS.get(cur, set())

    @staticmethod
    async def verify_resolution_eligibility(
        db: AsyncSession,
        incident: Incident,
        is_manual_signoff: bool = False,
        reason: Optional[str] = None,
    ) -> Tuple[bool, bool, str]:
        """
        Evaluates whether an incident is eligible to transition to 'resolved'.
        Returns: (is_eligible: bool, recovery_verified: bool, diagnostic_message: str)
        """
        # Load recovery actions for this incident
        stmt = (
            select(RecoveryAction)
            .options(selectinload(RecoveryAction.result))
            .where(RecoveryAction.incident_id == incident.id)
            .order_by(desc(RecoveryAction.requested_at))
        )
        res = await db.execute(stmt)
        recoveries = res.scalars().all()

        latest_rec: Optional[RecoveryAction] = recoveries[0] if recoveries else None
        recovery_verified = False

        if latest_rec:
            # Check if recovery execution and verification explicitly passed
            has_passed_verification = (
                latest_rec.verification == "passed"
                and latest_rec.result is not None
                and latest_rec.result.verified is True
            )
            if has_passed_verification:
                recovery_verified = True
            elif latest_rec.verification == "failed" or latest_rec.status == "failed":
                if not is_manual_signoff:
                    return (
                        False,
                        False,
                        f"Automated health verification failed for recovery '{latest_rec.id}'. "
                        "Incident must remain unresolved unless manual operator sign-off is explicitly provided.",
                    )
            elif latest_rec.status in ("running", "executing", "pending_approval", "approved"):
                if not is_manual_signoff:
                    return (
                        False,
                        False,
                        f"Recovery action '{latest_rec.id}' is still in progress (status: '{latest_rec.status}'). "
                        "An incident cannot be marked resolved simply because a recovery command was initiated.",
                    )

        if not recovery_verified and not is_manual_signoff:
            return (
                False,
                False,
                "Cannot resolve incident without verified healthy post-recovery telemetry. "
                "Explicit manual operator sign-off is required to manually resolve without verification.",
            )

        if is_manual_signoff:
            if not reason or len(reason.strip()) < 3:
                return (
                    False,
                    recovery_verified,
                    "Manual sign-off requires a mandatory explanatory reason.",
                )

        return True, recovery_verified, "Eligible for resolution."

    @classmethod
    async def transition(
        cls,
        db: AsyncSession,
        incident: Incident,
        target_status: str,
        reason: str,
        user: User,
        is_manual_signoff: bool = False,
    ) -> Incident:
        """
        Executes a validated lifecycle transition with audit logging and SSE broadcast.
        """
        clean_target = target_status.lower().strip()
        clean_current = incident.status.lower().strip()
        now = datetime.now(timezone.utc)
        actor_name = user.full_name or user.email
        actor_email = user.email

        if not reason or len(reason.strip()) < 3:
            raise IncidentResolutionIntegrityError(
                "A mandatory reason (minimum 3 characters) is required for all state transitions."
            )

        # 1. State machine transition validity check
        if clean_current == clean_target:
            raise IncidentResolutionIntegrityError(
                f"Incident '{incident.id}' is already in state '{clean_current}'."
            )

        if not cls.is_valid_transition(clean_current, clean_target):
            raise IncidentResolutionIntegrityError(
                f"Illegal transition: Cannot move incident '{incident.id}' from '{clean_current}' to '{clean_target}'. "
                f"Permitted transitions from '{clean_current}': {sorted(list(VALID_INCIDENT_TRANSITIONS.get(clean_current, set())))}"
            )

        # 2. Resolution gatekeeper checks
        if clean_target == "resolved":
            eligible, rec_verified, diag_msg = await cls.verify_resolution_eligibility(
                db=db,
                incident=incident,
                is_manual_signoff=is_manual_signoff,
                reason=reason,
            )
            if not eligible:
                raise IncidentResolutionIntegrityError(diag_msg)

            incident.status = "resolved"
            incident.resolved_at = now

            if is_manual_signoff:
                # Manual sign-off is separately recorded and cannot falsely claim recovery succeeded
                if rec_verified:
                    incident.recovery_status = f"Manual sign-off (recovery verified) by {actor_name}"
                    event_detail = f"Manual resolution sign-off granted by {actor_name} ({actor_email}) following verified recovery. Reason: {reason}"
                    event_tone = "success"
                else:
                    incident.recovery_status = f"Manual resolution by {actor_name} (recovery unverified)"
                    event_detail = f"Manual sign-off granted by {actor_name} ({actor_email}). Reason: {reason}. Note: Automated recovery was unverified."
                    event_tone = "neutral"

                db.add(IncidentEvent(
                    incident_id=incident.id,
                    label="Manual Resolution Sign-off",
                    detail=event_detail,
                    timestamp=now,
                    tone=event_tone,
                ))

                db.add(AuditLog(
                    organization_id=incident.organization_id,
                    user_id=user.id,
                    action="incident_manual_signoff",
                    resource_type="incident",
                    resource_id=incident.id,
                    details=json.dumps({
                        "actor": actor_email,
                        "actor_name": actor_name,
                        "previous_state": clean_current,
                        "new_state": "resolved",
                        "is_manual_signoff": True,
                        "recovery_verified": rec_verified,
                        "reason": reason,
                        "timestamp": now.isoformat(),
                    }),
                ))
            else:
                # Automated resolution verified
                incident.recovery_status = "Completed / Verified healthy"
                db.add(IncidentEvent(
                    incident_id=incident.id,
                    label="Incident Resolved",
                    detail=f"Automated resolution confirmed healthy. Reason: {reason}",
                    timestamp=now,
                    tone="success",
                ))
                db.add(AuditLog(
                    organization_id=incident.organization_id,
                    user_id=user.id,
                    action="incident_transition_resolved",
                    resource_type="incident",
                    resource_id=incident.id,
                    details=json.dumps({
                        "actor": actor_email,
                        "previous_state": clean_current,
                        "new_state": "resolved",
                        "recovery_verified": True,
                        "reason": reason,
                        "timestamp": now.isoformat(),
                    }),
                ))

        elif clean_target == "escalated":
            # Failed recovery can be escalated
            incident.status = "escalated"
            incident.recovery_status = f"Escalated to On-Call SRE: {reason}"
            db.add(IncidentEvent(
                incident_id=incident.id,
                label="Incident Escalated",
                detail=f"Incident escalated by {actor_name} ({actor_email}). Reason: {reason}",
                timestamp=now,
                tone="warning",
            ))
            db.add(AuditLog(
                organization_id=incident.organization_id,
                user_id=user.id,
                action="incident_escalated",
                resource_type="incident",
                resource_id=incident.id,
                details=json.dumps({
                    "actor": actor_email,
                    "previous_state": clean_current,
                    "new_state": "escalated",
                    "reason": reason,
                    "timestamp": now.isoformat(),
                }),
            ))

        else:
            # Other transitions: investigating, recovering, open
            incident.status = clean_target
            if clean_target == "investigating":
                incident.recovery_status = f"Under investigation ({actor_name})"
            elif clean_target == "recovering":
                incident.recovery_status = "Remediation in progress"
            elif clean_target == "open":
                incident.recovery_status = "Reopened"

            db.add(IncidentEvent(
                incident_id=incident.id,
                label=f"Status Changed: {clean_target.capitalize()}",
                detail=f"Transitioned from '{clean_current}' to '{clean_target}' by {actor_name}. Reason: {reason}",
                timestamp=now,
                tone="neutral",
            ))
            db.add(AuditLog(
                organization_id=incident.organization_id,
                user_id=user.id,
                action=f"incident_transition_{clean_target}",
                resource_type="incident",
                resource_id=incident.id,
                details=json.dumps({
                    "actor": actor_email,
                    "previous_state": clean_current,
                    "new_state": clean_target,
                    "reason": reason,
                    "timestamp": now.isoformat(),
                }),
            ))

        incident.updated_at = now

        # Add immutable transition audit record
        db.add(IncidentTransition(
            id=uuid.uuid4(),
            organization_id=incident.organization_id,
            incident_id=incident.id,
            actor_id=user.id,
            actor_email=actor_email,
            actor_role=getattr(user, "role", "operator"),
            previous_state=clean_current,
            new_state=clean_target,
            reason=reason.strip(),
            evidence_id=None,
            sign_off=bool(is_manual_signoff),
            created_at=now,
        ))

        await db.commit()

        # Reload incident with events and evidence
        reload_stmt = (
            select(Incident)
            .options(selectinload(Incident.events), selectinload(Incident.evidence))
            .where(Incident.id == incident.id)
        )
        reloaded = (await db.execute(reload_stmt)).scalar_one()

        # Emit real-time SSE event
        await event_broadcaster.broadcast(incident.organization_id, "incident_updated", {
            "id": incident.id,
            "status": incident.status,
            "recoveryStatus": incident.recovery_status,
            "resolvedAt": incident.resolved_at.isoformat() if incident.resolved_at else None,
        })

        return reloaded
