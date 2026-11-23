"""
AutoHeal DevOps — Recovery Policy Governance & Enforcement Engine
Evaluates organization, environment, agent, role, cooldown, and retry constraints before execution.
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Optional
import uuid
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import InfrastructureAgent
from app.models.recovery import RecoveryAction
from app.models.service import RecoveryPolicy, Service
from app.services.recovery.registry import APPROVED_RECOVERY_ACTIONS, is_action_allowed
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class PolicyEvaluationResult(BaseModel):
    """Structured decision output from the policy engine."""
    allowed: bool = Field(..., description="Whether the recovery operation is permitted by governance policy")
    requires_approval: bool = Field(True, description="Whether human-in-the-loop approval is mandatory")
    reason: str = Field(..., description="Explanation of policy decision or violation details")
    policy_id: Optional[str] = Field(None, description="Matched RecoveryPolicy UUID if configured")
    cooldown_remaining_seconds: int = Field(0, description="Remaining seconds before next attempt permitted")
    retry_count: int = Field(0, description="Number of attempts previously made for this incident")
    max_retries: int = Field(3, description="Configured maximum allowable retries before mandatory escalation")


class RecoveryPolicyEngine:
    """
    Authoritative policy enforcement layer.
    The AI model may recommend an action, but the policy engine independently
    determines whether execution is authorized under governance constraints.
    """

    async def evaluate_policy(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        service_id: str,
        action: str,
        operator_role: Optional[str] = None,
        agent_id: Optional[str] = None,
        incident_id: Optional[str] = None,
    ) -> PolicyEvaluationResult:
        """
        Comprehensive multi-factor governance evaluation.
        """
        clean_action = action.strip()

        # 1. Operation Allowlist Check
        if not is_action_allowed(clean_action):
            return PolicyEvaluationResult(
                allowed=False,
                requires_approval=True,
                reason=f"Security violation: Action '{clean_action}' is not in the approved recovery allowlist: {sorted(APPROVED_RECOVERY_ACTIONS)}",
            )

        # 2. Service & Tenant Isolation Check
        svc_stmt = select(Service).where(
            Service.id == service_id,
            Service.organization_id == organization_id,
        )
        svc_res = await db.execute(svc_stmt)
        service = svc_res.scalar_one_or_none()
        if not service:
            return PolicyEvaluationResult(
                allowed=False,
                requires_approval=True,
                reason=f"Service '{service_id}' was not found in organization '{organization_id}'.",
            )

        # 3. Environment Restriction Check
        if service.environment not in ("production", "staging", "local", "test"):
            return PolicyEvaluationResult(
                allowed=False,
                requires_approval=True,
                reason=f"Environment '{service.environment}' is not authorized for automated remediation.",
            )

        # 4. Operator Role Verification (if supplied)
        if operator_role and operator_role.lower() not in ("operator", "admin"):
            return PolicyEvaluationResult(
                allowed=False,
                requires_approval=True,
                reason=f"Role '{operator_role}' is not authorized to approve or execute recovery actions (requires operator or admin).",
            )

        # 5. Infrastructure Agent Verification (if designated)
        if agent_id:
            agent_stmt = select(InfrastructureAgent).where(
                InfrastructureAgent.id == agent_id,
                InfrastructureAgent.organization_id == organization_id,
            )
            agent_res = await db.execute(agent_stmt)
            agent = agent_res.scalar_one_or_none()
            if not agent:
                return PolicyEvaluationResult(
                    allowed=False,
                    requires_approval=True,
                    reason=f"Infrastructure agent '{agent_id}' does not belong to organization '{organization_id}'.",
                )
            if agent.status != "online":
                return PolicyEvaluationResult(
                    allowed=False,
                    requires_approval=True,
                    reason=f"Infrastructure agent '{agent_id}' is currently '{agent.status}' (must be online).",
                )
            if clean_action not in agent.capabilities:
                return PolicyEvaluationResult(
                    allowed=False,
                    requires_approval=True,
                    reason=f"Agent '{agent_id}' lacks required capability '{clean_action}'. Supported: {agent.capabilities}",
                )

        # 6. Retrieve configured RecoveryPolicy or apply strict enterprise defaults
        pol_stmt = select(RecoveryPolicy).where(
            RecoveryPolicy.service_id == service.id,
            RecoveryPolicy.action == clean_action,
            RecoveryPolicy.is_active == True,
        )
        pol_res = await db.execute(pol_stmt)
        policy = pol_res.scalar_one_or_none()

        cooldown_seconds = policy.cooldown_seconds if policy else 900  # Default 15 minutes
        if getattr(settings, "DEMO_MODE_ENABLED", False):
            # In live demo mode, shorten cooldown to 10s so presenters can demonstrate repeatedly to judges
            cooldown_seconds = min(cooldown_seconds, 10)
        max_retries = policy.max_retries if policy else 3
        approval_required = policy.approval_required if policy else True

        # 7. Check Cooldown Period
        # Query last completed execution for this service and action
        last_rec_stmt = (
            select(RecoveryAction)
            .where(
                RecoveryAction.service_id == service.id,
                RecoveryAction.action == clean_action,
                RecoveryAction.status == "completed",
            )
        )
        if incident_id:
            last_rec_stmt = last_rec_stmt.where(RecoveryAction.incident_id != incident_id)
        last_rec_stmt = last_rec_stmt.order_by(desc(RecoveryAction.requested_at)).limit(1)
        last_rec_res = await db.execute(last_rec_stmt)
        last_rec = last_rec_res.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if last_rec and last_rec.requested_at:
            last_time = last_rec.requested_at
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=timezone.utc)
            elapsed = (now - last_time).total_seconds()
            if elapsed < cooldown_seconds:
                remaining = int(cooldown_seconds - elapsed)
                return PolicyEvaluationResult(
                    allowed=False,
                    requires_approval=True,
                    reason=f"Anti-flapping guard: Service '{service.name}' is in recovery cooldown for another {remaining}s.",
                    policy_id=str(policy.id) if policy else None,
                    cooldown_remaining_seconds=remaining,
                    max_retries=max_retries,
                )

        # 8. Check Retry Limits for Incident
        retry_count = 0
        if incident_id:
            count_stmt = select(func.count(RecoveryAction.id)).where(
                RecoveryAction.incident_id == incident_id,
                RecoveryAction.status.in_(["failed", "completed"]),
            )
            retry_count = (await db.execute(count_stmt)).scalar() or 0
            if retry_count >= max_retries:
                return PolicyEvaluationResult(
                    allowed=False,
                    requires_approval=True,
                    reason=f"Retry limit exceeded: {retry_count} attempts already made (max: {max_retries}). Requiring human escalation.",
                    policy_id=str(policy.id) if policy else None,
                    retry_count=retry_count,
                    max_retries=max_retries,
                )

        return PolicyEvaluationResult(
            allowed=True,
            requires_approval=approval_required,
            reason="Recovery policy constraints satisfied.",
            policy_id=str(policy.id) if policy else None,
            retry_count=retry_count,
            max_retries=max_retries,
        )


policy_engine = RecoveryPolicyEngine()
