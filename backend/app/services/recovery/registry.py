"""
AutoHeal DevOps — Recovery Action Registry & Allowlist
Enforces strict least-privilege boundary against arbitrary code execution.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel


class RecoveryActionDefinition(BaseModel):
    action: str
    display_name: str
    description: str
    risk_level: str
    requires_approval: bool
    default_cooldown_seconds: int
    max_retries: int


RECOVERY_ACTION_REGISTRY: Dict[str, RecoveryActionDefinition] = {
    "restart_service": RecoveryActionDefinition(
        action="restart_service",
        display_name="Graceful Service Restart",
        description="Simulates sending SIGTERM to running worker processes, cycling containers, and re-binding socket listeners.",
        risk_level="low",
        requires_approval=True,
        default_cooldown_seconds=120,
        max_retries=3,
    ),
    "clear_cache": RecoveryActionDefinition(
        action="clear_cache",
        display_name="Purge Cache & Connection Pool",
        description="Simulates evicting stale in-memory cache partitions and cycling idle connection pool sockets.",
        risk_level="low",
        requires_approval=True,
        default_cooldown_seconds=60,
        max_retries=2,
    ),
    "scale_service": RecoveryActionDefinition(
        action="scale_service",
        display_name="Horizontal Replica Scale-Up",
        description="Simulates scaling the deployment replica count from N to N+2 to absorb throughput spikes.",
        risk_level="medium",
        requires_approval=True,
        default_cooldown_seconds=300,
        max_retries=2,
    ),
    "restore_health": RecoveryActionDefinition(
        action="restore_health",
        display_name="Reset Health Circuit Breaker",
        description="Simulates tripping open unhealthy circuit breakers and flushing queue backlogs.",
        risk_level="low",
        requires_approval=True,
        default_cooldown_seconds=60,
        max_retries=3,
    ),
    "rollback_release": RecoveryActionDefinition(
        action="rollback_release",
        display_name="Rollback to Previous Stable Release",
        description="Simulates reverting deployment container image to preceding verified semantic release tag.",
        risk_level="high",
        requires_approval=True,
        default_cooldown_seconds=600,
        max_retries=1,
    ),
}

APPROVED_RECOVERY_ACTIONS = set(RECOVERY_ACTION_REGISTRY.keys())


def is_action_allowed(action: str) -> bool:
    """Verifies that an action identifier exists in the approved allowlist."""
    return action in RECOVERY_ACTION_REGISTRY


def get_action_definition(action: str) -> Optional[RecoveryActionDefinition]:
    """Retrieves metadata definition for an allowlist action."""
    return RECOVERY_ACTION_REGISTRY.get(action)
