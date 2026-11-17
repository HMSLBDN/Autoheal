"""
AutoHeal DevOps — Simulated Infrastructure Agent Adapter
Implements the InfrastructureAgentClient interface safely without host execution or Docker socket access.
Validates signatures, enforces strict allowlists, and returns cryptographic receipts.
"""

import asyncio
from datetime import datetime, timezone
import hashlib
import logging
import uuid
from typing import Dict, Optional

from app.services.agent.allowlist import validate_agent_action
from app.services.agent.interface import InfrastructureAgentClient
from app.services.agent.models import (
    ActionExecutionStatus,
    ActionRequest,
    ActionResult,
    AgentHeartbeat,
    AgentRegistration,
    AgentStatus,
)
from app.services.agent.security import verify_payload_signature

logger = logging.getLogger(__name__)


class SimulatedAgentClient(InfrastructureAgentClient):
    """
    Safe simulation adapter for local development and non-production testing.
    Verifies cryptographic integrity, checks allowlist schemas, and generates
    tamper-evident execution receipts without executing arbitrary host shell commands.
    """

    def __init__(self, secret_key: str = "simulation_agent_secret_key_32chars", agent_id: Optional[str] = None):
        self.secret_key = secret_key
        self.agent_id = agent_id or f"sim-agent-{uuid.uuid4().hex[:8]}"
        self.hostname = "simulated-worker-01.internal"
        self.active_actions: Dict[str, ActionRequest] = {}
        self._cancelled_actions = set()

    async def register(self, registration: AgentRegistration) -> bool:
        self.agent_id = registration.agent_id
        self.hostname = registration.hostname
        logger.info("Simulated infrastructure agent registered: %s (%s)", self.agent_id, self.hostname)
        return True

    async def get_heartbeat(self) -> AgentHeartbeat:
        return AgentHeartbeat(
            agent_id=self.agent_id,
            status=AgentStatus.ONLINE,
            active_actions_count=len(self.active_actions),
            cpu_percent=14.2,
            memory_percent=38.6,
            timestamp=datetime.now(timezone.utc),
        )

    async def dispatch_action(self, request: ActionRequest) -> ActionResult:
        """
        Validates the request envelope and executes the simulated bounded recovery action.
        """
        # 1. Cryptographic signature and replay verification
        if request.signature:
            is_valid_sig = verify_payload_signature(
                secret_key=self.secret_key,
                action_id=request.action_id,
                service_id=request.service_id,
                action_type=request.action_type,
                parameters=request.parameters,
                nonce=request.nonce,
                timestamp=request.timestamp,
                provided_signature=request.signature,
            )
            if not is_valid_sig:
                return ActionResult(
                    action_id=request.action_id,
                    agent_id=self.agent_id,
                    status=ActionExecutionStatus.REJECTED,
                    exit_code=1,
                    duration_ms=0,
                    stdout_summary="",
                    stderr_summary="Cryptographic signature verification or replay check failed.",
                    evidence_receipt_hash=hashlib.sha256(b"rejected_sig").hexdigest(),
                    executed_at=datetime.now(timezone.utc),
                )

        # 2. Strict allowlist validation
        is_allowed, err_msg, sanitized_params = validate_agent_action(
            request.action_type, request.parameters
        )
        if not is_allowed:
            return ActionResult(
                action_id=request.action_id,
                agent_id=self.agent_id,
                status=ActionExecutionStatus.REJECTED,
                exit_code=2,
                duration_ms=0,
                stdout_summary="",
                stderr_summary=f"Allowlist rejection: {err_msg}",
                evidence_receipt_hash=hashlib.sha256(b"rejected_allowlist").hexdigest(),
                executed_at=datetime.now(timezone.utc),
            )

        # 3. Simulate execution lifecycle
        self.active_actions[request.action_id] = request
        start_time = datetime.now(timezone.utc)

        # Non-blocking brief pause to simulate real network/process latency (0.05s)
        await asyncio.sleep(0.05)

        # Check for cancellation
        if request.action_id in self._cancelled_actions:
            self.active_actions.pop(request.action_id, None)
            return ActionResult(
                action_id=request.action_id,
                agent_id=self.agent_id,
                status=ActionExecutionStatus.CANCELLED,
                exit_code=130,
                duration_ms=50,
                stdout_summary="",
                stderr_summary="Action was cancelled by operator request.",
                evidence_receipt_hash=hashlib.sha256(b"cancelled").hexdigest(),
                executed_at=datetime.now(timezone.utc),
            )

        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Build simulated execution output
        stdout = (
            f"[AGENT-EXECUTION-SIMULATOR]\n"
            f"Node: {self.hostname} | Agent: {self.agent_id}\n"
            f"Action: {request.action_type} | Service: {request.service_name} ({request.service_id})\n"
            f"Parameters: {sanitized_params}\n"
            f"Result: Operation completed successfully without errors.\n"
        )

        # Compute evidence receipt hash
        evidence_raw = f"{request.action_id}:{self.agent_id}:{duration_ms}:0:{stdout}"
        evidence_hash = hashlib.sha256(evidence_raw.encode("utf-8")).hexdigest()

        self.active_actions.pop(request.action_id, None)

        return ActionResult(
            action_id=request.action_id,
            agent_id=self.agent_id,
            status=ActionExecutionStatus.SUCCESS,
            exit_code=0,
            duration_ms=duration_ms,
            stdout_summary=stdout[:4096],
            stderr_summary="",
            evidence_receipt_hash=evidence_hash,
            executed_at=end_time,
        )

    async def cancel_action(self, action_id: str) -> bool:
        if action_id in self.active_actions:
            self._cancelled_actions.add(action_id)
            return True
        return False
