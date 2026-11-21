"""
AutoHeal DevOps — Recovery Orchestration Engine & State Machine
Enforces strict lifecycle state transitions, auditable progress tracking,
and backward-compatible frontend status mapping.
"""

from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Dict, List, Optional, Set
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.incident import Incident, IncidentEvent
from app.models.recovery import RecoveryAction
from app.services.events import event_broadcaster

logger = logging.getLogger(__name__)


class RecoveryState(str, Enum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    QUEUED = "queued"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


# Frontend Contract Aliases: Ensures backward compatibility with existing Next.js UI
FRONTEND_STATUS_MAP: Dict[RecoveryState, str] = {
    RecoveryState.PENDING: "pending_approval",
    RecoveryState.AWAITING_APPROVAL: "pending_approval",
    RecoveryState.APPROVED: "approved",
    RecoveryState.REJECTED: "rejected",
    RecoveryState.QUEUED: "running",
    RecoveryState.EXECUTING: "running",
    RecoveryState.VERIFYING: "running",
    RecoveryState.COMPLETED: "completed",
    RecoveryState.FAILED: "failed",
    RecoveryState.TIMED_OUT: "failed",
    RecoveryState.CANCELLED: "rejected",
}

# Permitted state transitions graph
VALID_TRANSITIONS: Dict[RecoveryState, Set[RecoveryState]] = {
    RecoveryState.PENDING: {
        RecoveryState.AWAITING_APPROVAL,
        RecoveryState.APPROVED,
        RecoveryState.REJECTED,
        RecoveryState.CANCELLED,
    },
    RecoveryState.AWAITING_APPROVAL: {
        RecoveryState.APPROVED,
        RecoveryState.EXECUTING,
        RecoveryState.REJECTED,
        RecoveryState.CANCELLED,
    },
    RecoveryState.APPROVED: {
        RecoveryState.QUEUED,
        RecoveryState.EXECUTING,
        RecoveryState.CANCELLED,
    },
    RecoveryState.QUEUED: {
        RecoveryState.EXECUTING,
        RecoveryState.TIMED_OUT,
        RecoveryState.CANCELLED,
    },
    RecoveryState.EXECUTING: {
        RecoveryState.VERIFYING,
        RecoveryState.COMPLETED,
        RecoveryState.FAILED,
        RecoveryState.TIMED_OUT,
    },
    RecoveryState.VERIFYING: {
        RecoveryState.COMPLETED,
        RecoveryState.FAILED,
        RecoveryState.TIMED_OUT,
    },
    RecoveryState.COMPLETED: set(),  # Terminal state
    RecoveryState.FAILED: set(),     # Terminal state
    RecoveryState.REJECTED: set(),   # Terminal state
    RecoveryState.TIMED_OUT: set(),  # Terminal state
    RecoveryState.CANCELLED: set(),  # Terminal state
}


class InvalidStateTransitionError(Exception):
    """Raised when an illegal lifecycle transition is attempted."""
    pass


def normalize_to_recovery_state(raw_status: str) -> RecoveryState:
    """Normalizes legacy frontend status strings into canonical RecoveryState enum."""
    clean = raw_status.strip().lower()
    if clean == "pending_approval":
        return RecoveryState.AWAITING_APPROVAL
    if clean == "running":
        return RecoveryState.EXECUTING
    try:
        return RecoveryState(clean)
    except ValueError:
        return RecoveryState.PENDING


class RecoveryOrchestrator:
    """
    Manages recovery state machine transitions, audit events, and broadcast notifications.
    """

    @staticmethod
    def can_transition(current: str, target: RecoveryState) -> bool:
        """Evaluates whether current status can transition to target status."""
        current_enum = normalize_to_recovery_state(current)
        return target in VALID_TRANSITIONS.get(current_enum, set())

    @staticmethod
    async def transition(
        db: AsyncSession,
        recovery: RecoveryAction,
        target_state: RecoveryState,
        reason: str,
        user_id: Optional[uuid.UUID] = None,
        organization_id: Optional[uuid.UUID] = None,
    ) -> RecoveryAction:
        """
        Executes a validated state transition with audit trails and real-time SSE broadcast.
        """
        current_state = normalize_to_recovery_state(recovery.status)

        # Self-transition is a no-op
        if current_state == target_state:
            return recovery

        if not RecoveryOrchestrator.can_transition(recovery.status, target_state):
            raise InvalidStateTransitionError(
                f"Illegal transition: Cannot move recovery '{recovery.id}' from '{current_state.value}' to '{target_state.value}'."
            )

        now = datetime.now(timezone.utc)
        old_status = recovery.status
        frontend_status = FRONTEND_STATUS_MAP[target_state]
        recovery.status = frontend_status

        # Update timestamps / duration
        if target_state == RecoveryState.COMPLETED and recovery.result:
            recovery.result.completed_at = now
        elif target_state == RecoveryState.EXECUTING:
            recovery.duration_seconds = 15

        # Create audit log record
        db.add(AuditLog(
            organization_id=organization_id,
            user_id=user_id,
            action=f"recovery_state_{target_state.value}",
            resource_type="recovery_action",
            resource_id=recovery.id,
            details=f"Recovery state transitioned from '{old_status}' to '{target_state.value}'. Reason: {reason}",
        ))

        # Create incident timeline event
        tone_map = {
            RecoveryState.APPROVED: "neutral",
            RecoveryState.EXECUTING: "neutral",
            RecoveryState.VERIFYING: "neutral",
            RecoveryState.COMPLETED: "success",
            RecoveryState.FAILED: "warning",
            RecoveryState.REJECTED: "warning",
            RecoveryState.TIMED_OUT: "warning",
            RecoveryState.CANCELLED: "warning",
        }

        db.add(IncidentEvent(
            incident_id=recovery.incident_id,
            label=f"Recovery {target_state.value.capitalize().replace('_', ' ')}",
            detail=reason,
            timestamp=now,
            tone=tone_map.get(target_state, "neutral"),
        ))

        await db.flush()

        # Real-time SSE event emission
        if organization_id:
            await event_broadcaster.broadcast(organization_id, "recovery_updated", {
                "id": recovery.id,
                "status": recovery.status,
                "canonicalState": target_state.value,
                "verification": recovery.verification,
            })

        return recovery


orchestrator = RecoveryOrchestrator()
