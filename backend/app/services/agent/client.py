"""
AutoHeal DevOps — Remote Infrastructure Agent Client
Production adapter connecting to isolated remote agent daemons over mTLS/HTTP with signed payloads.
"""

from datetime import datetime, timezone
import hashlib
import logging
import uuid
from typing import Optional
import httpx

from app.services.agent.interface import InfrastructureAgentClient
from app.services.agent.models import (
    ActionExecutionStatus,
    ActionRequest,
    ActionResult,
    AgentHeartbeat,
    AgentRegistration,
    AgentStatus,
)
from app.services.agent.security import sign_payload

logger = logging.getLogger(__name__)


class RemoteAgentClient(InfrastructureAgentClient):
    """
    Client for dispatching signed actions to remote infrastructure nodes running the AutoHeal agent daemon.
    """

    def __init__(
        self,
        agent_url: str,
        secret_key: str,
        agent_id: Optional[str] = None,
        cert_path: Optional[str] = None,
        key_path: Optional[str] = None,
    ):
        self.agent_url = agent_url.rstrip("/")
        self.secret_key = secret_key
        self.agent_id = agent_id or "remote-agent"
        self.cert = (cert_path, key_path) if cert_path and key_path else None

    async def register(self, registration: AgentRegistration) -> bool:
        try:
            async with httpx.AsyncClient(cert=self.cert, timeout=10.0) as client:
                resp = await client.post(
                    f"{self.agent_url}/api/v1/agent/register",
                    json=registration.model_dump(mode="json"),
                )
                return resp.status_code in (200, 201)
        except Exception as e:
            logger.error("Failed to register with remote agent %s: %s", self.agent_url, e)
            return False

    async def get_heartbeat(self) -> AgentHeartbeat:
        try:
            async with httpx.AsyncClient(cert=self.cert, timeout=5.0) as client:
                resp = await client.get(f"{self.agent_url}/api/v1/agent/heartbeat")
                if resp.status_code == 200:
                    return AgentHeartbeat(**resp.json())
        except Exception as e:
            logger.warning("Agent heartbeat check failed for %s: %s", self.agent_url, e)

        return AgentHeartbeat(
            agent_id=self.agent_id,
            status=AgentStatus.OFFLINE,
            active_actions_count=0,
            cpu_percent=0.0,
            memory_percent=0.0,
            timestamp=datetime.now(timezone.utc),
        )

    async def dispatch_action(self, request: ActionRequest) -> ActionResult:
        """
        Signs the envelope and posts to the remote agent daemon.
        """
        if not request.signature:
            timestamp_iso = request.timestamp.isoformat()
            request.signature = sign_payload(
                secret_key=self.secret_key,
                action_id=request.action_id,
                service_id=request.service_id,
                action_type=request.action_type,
                parameters=request.parameters,
                nonce=request.nonce,
                timestamp_iso=timestamp_iso,
            )

        start_time = datetime.now(timezone.utc)
        try:
            async with httpx.AsyncClient(cert=self.cert, timeout=float(request.timeout_seconds + 5)) as client:
                resp = await client.post(
                    f"{self.agent_url}/api/v1/agent/actions/execute",
                    json=request.model_dump(mode="json"),
                )
                if resp.status_code == 200:
                    return ActionResult(**resp.json())
                else:
                    return ActionResult(
                        action_id=request.action_id,
                        agent_id=self.agent_id,
                        status=ActionExecutionStatus.FAILED,
                        exit_code=resp.status_code,
                        duration_ms=int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
                        stdout_summary="",
                        stderr_summary=f"Agent returned HTTP {resp.status_code}: {resp.text[:500]}",
                        evidence_receipt_hash=hashlib.sha256(b"http_error").hexdigest(),
                        executed_at=datetime.now(timezone.utc),
                    )
        except httpx.TimeoutException:
            return ActionResult(
                action_id=request.action_id,
                agent_id=self.agent_id,
                status=ActionExecutionStatus.TIMEOUT,
                exit_code=124,
                duration_ms=request.timeout_seconds * 1000,
                stdout_summary="",
                stderr_summary=f"Action execution timed out after {request.timeout_seconds}s.",
                evidence_receipt_hash=hashlib.sha256(b"timeout").hexdigest(),
                executed_at=datetime.now(timezone.utc),
            )
        except Exception as e:
            return ActionResult(
                action_id=request.action_id,
                agent_id=self.agent_id,
                status=ActionExecutionStatus.FAILED,
                exit_code=255,
                duration_ms=int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
                stdout_summary="",
                stderr_summary=f"Network or agent communication error: {str(e)}",
                evidence_receipt_hash=hashlib.sha256(b"comm_error").hexdigest(),
                executed_at=datetime.now(timezone.utc),
            )

    async def cancel_action(self, action_id: str) -> bool:
        try:
            async with httpx.AsyncClient(cert=self.cert, timeout=5.0) as client:
                resp = await client.post(f"{self.agent_url}/api/v1/agent/actions/{action_id}/cancel")
                return resp.status_code == 200
        except Exception as e:
            logger.error("Failed to cancel action %s on %s: %s", action_id, self.agent_url, e)
            return False
