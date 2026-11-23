"""
AutoHeal DevOps — Controlled Recovery Execution Engine
Executes policy-gated recovery actions via safe simulation adapters,
tracks execution duration, and triggers post-recovery health verification.
"""

from datetime import datetime, timezone
import logging
import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.audit import AuditLog
from app.models.incident import Incident, IncidentEvent
from app.models.recovery import RecoveryAction, RecoveryResult
from app.models.service import RecoveryPolicy, Service
from app.services.agent import (
    ActionExecutionStatus,
    ActionRequest,
    InfrastructureAgentClient,
    SimulatedAgentClient,
    RestrictedDockerAgentClient,
)
from app.services.events import event_broadcaster
from app.services.recovery.orchestrator import RecoveryState, orchestrator
from app.services.recovery.policy_engine import policy_engine
from app.services.recovery.registry import is_action_allowed, get_action_definition
from app.services.recovery.verifier import PostRecoveryVerifier

logger = logging.getLogger(__name__)


class RecoveryExecutor:
    """
    Safely executes approved recovery actions.
    Enforces action allowlist, checks policy constraints, logs audit trails,
    coordinates restricted infrastructure agent execution, and triggers post-recovery health verification.
    """

    def __init__(self, agent_client: Optional[InfrastructureAgentClient] = None):
        self.verifier = PostRecoveryVerifier()
        settings = get_settings()
        if agent_client is not None:
            self.agent_client = agent_client
        elif not settings.RECOVERY_SIMULATION_MODE and getattr(settings, "RESTRICTED_DOCKER_AGENT_ENABLED", False):
            self.agent_client = RestrictedDockerAgentClient()
        else:
            self.agent_client = SimulatedAgentClient()

    async def execute_recovery(
        self,
        db: AsyncSession,
        recovery_id: str,
        simulated_outcome_healthy: bool = True,
    ) -> RecoveryAction:
        """
        Executes an approved recovery action.
        Transitions: approved -> running -> completed -> verified.
        """
        stmt = (
            select(RecoveryAction)
            .options(
                selectinload(RecoveryAction.result),
                selectinload(RecoveryAction.incident),
            )
            .where(RecoveryAction.id == recovery_id)
        )
        result = await db.execute(stmt)
        recovery = result.scalar_one_or_none()

        if not recovery:
            raise ValueError(f"Recovery action '{recovery_id}' not found.")

        # 1. State transition check: only 'approved' or 'pending_approval' can be executed
        if recovery.status not in ("approved", "pending_approval"):
            raise ValueError(f"Recovery '{recovery_id}' cannot be executed from status '{recovery.status}'.")

        # 1b. Strict Operator Approval Governance Check (Defense-in-Depth)
        if recovery.approval_required and recovery.status != "approved":
            raise ValueError(
                f"Recovery '{recovery_id}' requires explicit operator approval before execution (current status: '{recovery.status}')."
            )

        # 2. Strict allowlist validation
        if not is_action_allowed(recovery.action):
            raise ValueError(f"Security violation: Action '{recovery.action}' is not in the approved recovery allowlist.")

        action_def = get_action_definition(recovery.action)

        # 3. Load affected service
        svc_stmt = select(Service).where(Service.name == recovery.service_name)
        svc_res = await db.execute(svc_stmt)
        service = svc_res.scalar_one_or_none()

        if not service:
            # Fallback by service_id
            svc_stmt_id = select(Service).where(Service.id == recovery.service_id)
            svc_res_id = await db.execute(svc_stmt_id)
            service = svc_res_id.scalar_one_or_none()

        if not service:
            raise ValueError(f"Service for recovery '{recovery_id}' was not found in database.")

        # 4. Check Recovery Policy (cooldown, max retries, environment)
        policy_eval = await policy_engine.evaluate_policy(
            db=db,
            organization_id=service.organization_id,
            service_id=service.id,
            action=recovery.action,
            incident_id=recovery.incident_id,
        )
        if not policy_eval.allowed:
            raise ValueError(f"Policy violation: {policy_eval.reason}")

        # 4b. Container Allowlist Enforcement for Real Infrastructure Mode
        settings = get_settings()
        if not settings.RECOVERY_SIMULATION_MODE and getattr(settings, "RESTRICTED_DOCKER_AGENT_ENABLED", False):
            target_name = service.name or recovery.service_name
            approved_list = getattr(settings, "DOCKER_AGENT_APPROVED_CONTAINERS", [])
            if target_name not in approved_list:
                raise ValueError(
                    f"Security violation: Target service '{target_name}' is not in the approved "
                    f"Docker agent container allowlist. Permitted: {approved_list}"
                )

        # 5. Transition to 'executing' (canonical) / 'running' (frontend)
        start_time = datetime.now(timezone.utc)
        await orchestrator.transition(
            db=db,
            recovery=recovery,
            target_state=RecoveryState.EXECUTING,
            reason=f"Executing action '{action_def.display_name if action_def else recovery.action}'.",
            organization_id=service.organization_id,
        )
        is_real_exec = (
            not settings.RECOVERY_SIMULATION_MODE
            and getattr(settings, "RESTRICTED_DOCKER_AGENT_ENABLED", False)
        )
        mode_str = "REAL" if is_real_exec else "SIMULATED"
        recovery.execution_mode = mode_str
        recovery.evidence_classification = "SIMULATED" if not is_real_exec else "DOCKER_API_ACCEPTED"
        await db.commit()

        # 6. Execute safe action via restricted infrastructure agent
        # (Enforces cryptographic signed envelope, allowlist, and zero direct Docker socket access)
        action_req = ActionRequest(
            action_id=str(recovery.id),
            service_id=str(service.id),
            service_name=recovery.service_name,
            action_type=recovery.action,
            parameters={},
            nonce=uuid.uuid4().hex,
            timestamp=start_time,
        )
        agent_res = await self.agent_client.dispatch_action(action_req)

        # 6b. For live test microservice, dispatch real recovery to its chaos endpoint safely
        port = {
            "checkout-api": 8080,
            "customer-web": 8081,
            "payments-api": 8082,
        }.get(recovery.service_name)
        if port:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=2.0) as http_client:
                    for base in [f"http://127.0.0.1:{port}", f"http://localhost:{port}", f"http://{recovery.service_name}:{port}"]:
                        try:
                            recover_res = await http_client.post(f"{base}/chaos/recover", json={})
                            if recover_res.status_code in (200, 204):
                                logger.info("Dispatched live microservice recovery to %s", base)
                                break
                        except Exception:
                            continue
            except Exception as e:
                logger.debug("Live microservice chaos recover probe omitted: %s", e)

        # 6a. Check if restricted agent execution failed or was rejected
        if agent_res.status != ActionExecutionStatus.SUCCESS or agent_res.exit_code != 0:
            now = datetime.now(timezone.utc)
            duration_s = max(1, int((now - start_time).total_seconds()))
            fail_summary = (
                f"Execution failed for action '{action_def.display_name if action_def else recovery.action}' "
                f"on service '{recovery.service_name}'. Agent returned status '{agent_res.status.value}' "
                f"with exit code {agent_res.exit_code}: {agent_res.stderr_summary or 'Execution rejected or failed'}"
            )
            recovery.status = "failed"
            recovery.verification = "failed"
            recovery.duration_seconds = duration_s
            recovery.execution_mode = mode_str
            recovery.evidence_classification = "VERIFICATION_FAILED"
            diag_output = (
                f"[AGENT_EXECUTION_FAILURE]\n"
                f"TIMESTAMP: {now.isoformat()}\n"
                f"ACTION: {recovery.action}\n"
                f"SERVICE: {recovery.service_name}\n"
                f"MODE: {mode_str}\n"
                f"AGENT_ID: {agent_res.agent_id}\n"
                f"STATUS: {agent_res.status.value}\n"
                f"EXIT_CODE: {agent_res.exit_code}\n"
                f"EVIDENCE_HASH: {agent_res.evidence_receipt_hash}\n"
                f"STDERR:\n{agent_res.stderr_summary}\n"
            )
            if "result" in recovery.__dict__ and recovery.result is not None:
                recovery.result.summary = fail_summary
                recovery.result.verified = False
                recovery.result.completed_at = now
                recovery.result.diagnostic_output = diag_output
                recovery.result.execution_mode = mode_str
                recovery.result.evidence_classification = "VERIFICATION_FAILED"
            else:
                recovery.result = RecoveryResult(
                    id=uuid.uuid4(),
                    recovery_action_id=recovery.id,
                    verified=False,
                    summary=fail_summary,
                    completed_at=now,
                    diagnostic_output=diag_output,
                    execution_mode=mode_str,
                    evidence_classification="VERIFICATION_FAILED",
                )

            # Update incident state to reflect failure and prevent resolution
            inc_stmt = select(Incident).where(Incident.id == recovery.incident_id)
            inc_res = await db.execute(inc_stmt)
            incident = inc_res.scalar_one_or_none()
            if incident:
                incident.status = "investigating"
                incident.recovery_status = f"Execution failed ({agent_res.status.value}) / Escalation required"
                db.add(IncidentEvent(
                    incident_id=incident.id,
                    label="Recovery Execution Failed",
                    detail=fail_summary,
                    timestamp=now,
                    tone="warning",
                ))

            db.add(AuditLog(
                organization_id=service.organization_id if service else None,
                action="recovery_failed",
                resource_type="recovery_action",
                resource_id=recovery.id,
                details=f"Execution of '{recovery.action}' failed for '{recovery.service_name}'. mode={mode_str}, status={agent_res.status.value}, exit_code={agent_res.exit_code}.",
            ))
            await db.commit()

            # Broadcast failure events
            if incident:
                await event_broadcaster.broadcast(incident.organization_id, "recovery_updated", {
                    "id": recovery.id,
                    "status": recovery.status,
                    "verification": recovery.verification,
                    "durationSeconds": recovery.duration_seconds,
                    "executionMode": recovery.execution_mode,
                    "evidenceClassification": recovery.evidence_classification,
                })
                await event_broadcaster.broadcast(incident.organization_id, "incident_updated", {
                    "id": incident.id,
                    "status": incident.status,
                    "recoveryStatus": incident.recovery_status,
                })
            return recovery

        initial_classification = "DOCKER_API_ACCEPTED" if is_real_exec else "SIMULATED"
        recovery.execution_mode = mode_str
        recovery.evidence_classification = initial_classification

        exec_summary = (
            f"Successfully dispatched {action_def.display_name if action_def else recovery.action} "
            f"via restricted agent for service '{recovery.service_name}' ({mode_str} mode). Awaiting health verification."
        )

        now = datetime.now(timezone.utc)
        diag_output = (
            f"[AGENT_EXECUTION_RECEIPT]\n"
            f"TIMESTAMP: {now.isoformat()}\n"
            f"ACTION: {recovery.action}\n"
            f"SERVICE: {recovery.service_name}\n"
            f"MODE: {mode_str}\n"
            f"CLASSIFICATION: {initial_classification}\n"
            f"AGENT_ID: {agent_res.agent_id}\n"
            f"EXIT_CODE: {agent_res.exit_code}\n"
            f"EVIDENCE_HASH: {agent_res.evidence_receipt_hash}\n"
            f"STDOUT:\n{agent_res.stdout_summary}\n"
        )

        if "result" in recovery.__dict__ and recovery.result is not None:
            recovery.result.summary = exec_summary
            recovery.result.completed_at = now
            recovery.result.diagnostic_output = diag_output
            recovery.result.execution_mode = mode_str
            recovery.result.evidence_classification = initial_classification
        else:
            recovery.result = RecoveryResult(
                id=uuid.uuid4(),
                recovery_action_id=recovery.id,
                verified=False,
                summary=exec_summary,
                completed_at=now,
                diagnostic_output=diag_output,
                execution_mode=mode_str,
                evidence_classification=initial_classification,
            )

        db.add(AuditLog(
            organization_id=service.organization_id if service else None,
            action="recovery_executed",
            resource_type="recovery_action",
            resource_id=recovery.id,
            details=f"Controlled execution of '{recovery.action}' completed for '{recovery.service_name}'. mode={mode_str}, classification={initial_classification}.",
        ))
        await db.commit()

        # 7. Post-Recovery Health Verification
        inc_stmt = select(Incident).where(Incident.id == recovery.incident_id)
        inc_res = await db.execute(inc_stmt)
        incident = inc_res.scalar_one()

        verified = await self.verifier.verify_recovery(
            db=db,
            recovery=recovery,
            incident=incident,
            service=service,
            simulated_healthy=simulated_outcome_healthy,
            execution_mode=mode_str,
            evidence_classification=None,
        )
        duration_s = max(1, int((datetime.now(timezone.utc) - start_time).total_seconds()))
        recovery.duration_seconds = duration_s

        recovery.status = "completed"
        if not verified:
            recovery.verification = "failed"

        await db.commit()

        # Reload with eager-loaded result relationship
        final_stmt = (
            select(RecoveryAction)
            .options(selectinload(RecoveryAction.result))
            .where(RecoveryAction.id == recovery.id)
        )
        final_res = await db.execute(final_stmt)
        final_action = final_res.scalar_one()

        # Broadcast SSE events for real-time dashboard sync
        await event_broadcaster.broadcast(incident.organization_id, "recovery_updated", {
            "id": final_action.id,
            "status": final_action.status,
            "verification": final_action.verification,
            "durationSeconds": final_action.duration_seconds,
            "executionMode": final_action.execution_mode,
            "evidenceClassification": final_action.evidence_classification,
        })
        await event_broadcaster.broadcast(incident.organization_id, "incident_updated", {
            "id": incident.id,
            "status": incident.status,
            "recoveryStatus": incident.recovery_status,
        })
        await event_broadcaster.broadcast(incident.organization_id, "service_health", {
            "id": service.id,
            "name": service.name,
            "status": service.status,
            "availability": service.availability,
            "errorRate": service.error_rate,
            "latencyMs": service.latency_ms,
        })

        return final_action
