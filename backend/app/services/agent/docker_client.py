"""
AutoHeal DevOps — Restricted Docker Agent Client
Connects the FastAPI control plane to the standalone Restricted Docker Agent over authenticated HTTP.
Enforces HMAC-SHA256 request signing, nonces, and timeout boundaries.
"""

from datetime import datetime, timezone
import hashlib
import logging
from typing import Optional
import uuid
import httpx

from app.config import get_settings
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
settings = get_settings()


class RestrictedDockerAgentClient(InfrastructureAgentClient):
    """
    HTTP client for dispatching signed recovery actions to the standalone Restricted Docker Agent.
    """

    def __init__(
        self,
        agent_url: Optional[str] = None,
        secret_key: Optional[str] = None,
        agent_id: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ):
        self.agent_url = (agent_url or settings.DOCKER_AGENT_URL).rstrip("/")
        self.secret_key = secret_key or settings.DOCKER_AGENT_SECRET_KEY
        self.agent_id = agent_id or "docker-agent-restricted-01"
        self.timeout = timeout_seconds

    async def register(self, registration: AgentRegistration) -> bool:
        """Verifies connectivity with the restricted Docker agent."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.agent_url}/health")
                return resp.status_code == 200
        except Exception as e:
            logger.warning("Failed to ping restricted Docker agent at %s: %s", self.agent_url, e)
            return False

    async def get_heartbeat(self) -> AgentHeartbeat:
        """Queries health and status from the restricted Docker agent."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.agent_url}/health")
                if resp.status_code == 200:
                    data = resp.json()
                    return AgentHeartbeat(
                        agent_id=data.get("agent_id", self.agent_id),
                        status=AgentStatus.ONLINE if data.get("status") == "healthy" else AgentStatus.DEGRADED,
                        active_actions_count=0,
                        cpu_percent=10.0,
                        memory_percent=25.0,
                        timestamp=datetime.now(timezone.utc),
                    )
        except Exception as e:
            logger.warning("Heartbeat probe failed for agent %s: %s", self.agent_url, e)

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
        Signs the command payload and dispatches it to the restricted agent's execute endpoint.
        """
        now = datetime.now(timezone.utc)
        nonce = request.nonce or uuid.uuid4().hex
        timestamp_iso = (request.timestamp or now).isoformat()

        # Sign payload using HMAC-SHA256
        signature = sign_payload(
            secret_key=self.secret_key,
            action_id=request.action_id,
            service_id=request.service_name,  # target_container
            action_type=request.action_type,
            parameters=request.parameters,
            nonce=nonce,
            timestamp_iso=timestamp_iso,
        )

        payload = {
            "action_id": request.action_id,
            "target_container": request.service_name,
            "action_type": request.action_type,
            "parameters": request.parameters,
            "timeout_seconds": request.timeout_seconds,
            "nonce": nonce,
            "timestamp": timestamp_iso,
            "signature": signature,
            "correlation_id": f"corr-{uuid.uuid4().hex[:10]}",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.agent_url}/api/v1/actions/execute",
                    json=payload,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    status_str = data.get("status", "success").lower()
                    status_enum = ActionExecutionStatus.SUCCESS if status_str == "success" else ActionExecutionStatus.FAILED
                    return ActionResult(
                        action_id=request.action_id,
                        agent_id=self.agent_id,
                        status=status_enum,
                        exit_code=data.get("exit_code", 0),
                        duration_ms=data.get("duration_ms", 50),
                        stdout_summary=data.get("stdout", "")[:4096],
                        stderr_summary=data.get("stderr", "")[:4096],
                        evidence_receipt_hash=data.get("evidence_receipt_hash", hashlib.sha256(b"receipt").hexdigest()),
                        executed_at=datetime.now(timezone.utc),
                    )
                elif resp.status_code in (401, 403):
                    detail = resp.json().get("detail", "Authorization or allowlist rejected")
                    logger.warning("Restricted Docker Agent rejected action %s: %s", request.action_id, detail)
                    return ActionResult(
                        action_id=request.action_id,
                        agent_id=self.agent_id,
                        status=ActionExecutionStatus.REJECTED,
                        exit_code=2,
                        duration_ms=10,
                        stdout_summary="",
                        stderr_summary=f"Agent security rejection: {detail}",
                        evidence_receipt_hash=hashlib.sha256(f"rejected:{detail}".encode("utf-8")).hexdigest(),
                        executed_at=datetime.now(timezone.utc),
                    )
                else:
                    detail = resp.text[:500]
                    return ActionResult(
                        action_id=request.action_id,
                        agent_id=self.agent_id,
                        status=ActionExecutionStatus.FAILED,
                        exit_code=1,
                        duration_ms=10,
                        stdout_summary="",
                        stderr_summary=f"Agent HTTP error {resp.status_code}: {detail}",
                        evidence_receipt_hash=hashlib.sha256(b"agent_http_error").hexdigest(),
                        executed_at=datetime.now(timezone.utc),
                    )

        except httpx.TimeoutException:
            logger.error("Restricted Docker Agent timed out executing action %s", request.action_id)
            return ActionResult(
                action_id=request.action_id,
                agent_id=self.agent_id,
                status=ActionExecutionStatus.TIMEOUT,
                exit_code=124,
                duration_ms=int(self.timeout * 1000),
                stdout_summary="",
                stderr_summary=f"Action timed out after {self.timeout}s waiting for agent response.",
                evidence_receipt_hash=hashlib.sha256(b"timeout").hexdigest(),
                executed_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            logger.exception("Failed to connect to Restricted Docker Agent at %s: %s", self.agent_url, exc)
            return ActionResult(
                action_id=request.action_id,
                agent_id=self.agent_id,
                status=ActionExecutionStatus.FAILED,
                exit_code=1,
                duration_ms=0,
                stdout_summary="",
                stderr_summary=f"Connection failure to Restricted Docker Agent: {str(exc)}",
                evidence_receipt_hash=hashlib.sha256(b"conn_error").hexdigest(),
                executed_at=datetime.now(timezone.utc),
            )

    async def cancel_action(self, action_id: str) -> bool:
        """Action cancellation is unsupported once dispatched to Docker."""
        return False
