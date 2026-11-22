"""
Restricted Docker Agent — FastAPI HTTP Server
Exposes authenticated REST endpoints for allowlisted Docker management.
FastAPI control plane connects here over internal network; direct Docker socket is never exposed to backend.
"""

from datetime import datetime, timezone
import hashlib
import hmac
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse

from docker_agent.allowlist import validate_operation_allowlist, APPROVED_CONTAINERS, ALLOWED_OPERATIONS
from docker_agent.audit import audit_logger
from docker_agent.config import settings
from docker_agent.docker_client import DockerEngineClient
from docker_agent.metrics import agent_metrics
from docker_agent.models import (
    ActionExecutionRequest,
    ActionExecutionResponse,
    ActionStatus,
    ActionType,
    AgentHealthResponse,
    ContainerStatus,
)
from docker_agent.security import (
    validate_container_name_security,
    verify_payload_signature,
)
from docker_agent.verifier import ApplicationHealthVerifier

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AutoHeal Restricted Docker Agent",
    version="0.1.0",
    description="Secure, isolated execution agent with strict allowlists and zero arbitrary shell access.",
)

# Startup timestamp for uptime calculation
STARTUP_TIME = time.time()

# Shared singleton clients
docker_client = DockerEngineClient(
    socket_path=settings.DOCKER_SOCKET_PATH,
    mock_mode=settings.ENABLE_MOCK_FALLBACK,
)
health_verifier = ApplicationHealthVerifier()


@app.get("/health", response_model=AgentHealthResponse, tags=["Health"])
def get_agent_health():
    """Returns agent liveness, Docker daemon connectivity, and allowlisted boundaries."""
    uptime = int(time.time() - STARTUP_TIME)
    docker_ok = docker_client.ping()

    return AgentHealthResponse(
        status="healthy" if docker_ok else "degraded",
        agent_id=settings.AGENT_ID,
        version="0.1.0",
        uptime_seconds=uptime,
        docker_available=docker_ok,
        approved_containers=sorted(list(settings.APPROVED_CONTAINERS)),
        allowed_operations=sorted(list(ALLOWED_OPERATIONS)),
    )


@app.get("/metrics", response_class=PlainTextResponse, tags=["Observability"])
def get_metrics():
    """Exposes Prometheus-compatible operational metrics."""
    return agent_metrics.format_prometheus_metrics()


@app.get(
    "/api/v1/containers/{container_name}/status",
    response_model=ContainerStatus,
    tags=["Inspection"],
)
def get_container_status(container_name: str):
    """
    Retrieves current state and health of an approved container.
    Rejects any unapproved or non-whitelisted container names.
    """
    valid, err = validate_container_name_security(container_name)
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    if container_name not in settings.APPROVED_CONTAINERS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Container '{container_name}' is not in the approved allowlist.",
        )

    try:
        return docker_client.inspect_container(container_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post(
    "/api/v1/actions/execute",
    response_model=ActionExecutionResponse,
    tags=["Execution"],
)
async def execute_action(action_req: ActionExecutionRequest, request: Request):
    """
    Executes a cryptographically signed, allowlisted recovery operation against an approved container.
    Rejects unauthorized, replayed, expired, or non-whitelisted requests.
    """
    start_time = time.time()
    agent_metrics.record_request_received()
    client_ip = request.client.host if request.client else "unknown"

    # 1. Container identifier security validation
    is_safe_name, name_err = validate_container_name_security(action_req.target_container)
    if not is_safe_name:
        agent_metrics.record_rejected(reason="malformed_container_name")
        audit_logger.record_event(
            event_type="security_rejection",
            action_id=action_req.action_id,
            target_container=action_req.target_container,
            action_type=action_req.action_type,
            status=ActionStatus.REJECTED.value,
            exit_code=2,
            duration_ms=0,
            evidence_hash=hashlib.sha256(b"rejected_malformed_name").hexdigest(),
            details=name_err,
            correlation_id=action_req.correlation_id,
            client_ip=client_ip,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=name_err)

    # 2. Cryptographic signature and anti-replay verification
    sig_ok, sig_err = verify_payload_signature(
        secret_key=settings.AGENT_SECRET_KEY,
        action_id=action_req.action_id,
        target_container=action_req.target_container,
        action_type=action_req.action_type,
        parameters=action_req.parameters,
        nonce=action_req.nonce,
        timestamp=action_req.timestamp,
        provided_signature=action_req.signature,
        max_drift_seconds=settings.MAX_TIMESTAMP_DRIFT_SECONDS,
        nonce_ttl_seconds=settings.REPLAY_CACHE_TTL_SECONDS,
    )
    if not sig_ok:
        agent_metrics.record_rejected(reason=sig_err)
        audit_logger.record_event(
            event_type="security_rejection",
            action_id=action_req.action_id,
            target_container=action_req.target_container,
            action_type=action_req.action_type,
            status=ActionStatus.REJECTED.value,
            exit_code=1,
            duration_ms=0,
            evidence_hash=hashlib.sha256(b"rejected_signature").hexdigest(),
            details=sig_err,
            correlation_id=action_req.correlation_id,
            client_ip=client_ip,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=sig_err)

    # 3. Independent Server-Side Allowlist Enforcement
    is_allowed, allow_err, sanitized_params = validate_operation_allowlist(
        target_container=action_req.target_container,
        action_type=action_req.action_type,
        parameters=action_req.parameters,
        custom_approved_containers=settings.APPROVED_CONTAINERS,
    )
    if not is_allowed:
        agent_metrics.record_rejected(reason=allow_err)
        audit_logger.record_event(
            event_type="policy_rejection",
            action_id=action_req.action_id,
            target_container=action_req.target_container,
            action_type=action_req.action_type,
            status=ActionStatus.REJECTED.value,
            exit_code=2,
            duration_ms=0,
            evidence_hash=hashlib.sha256(b"rejected_allowlist").hexdigest(),
            details=allow_err,
            correlation_id=action_req.correlation_id,
            client_ip=client_ip,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=allow_err)

    # 4. Request is fully authorized
    agent_metrics.record_authorized()

    # 5. Dispatch Allowlisted Operation
    action_type = action_req.action_type.strip().lower()

    # Enforce Simulation Mode Lock: prevent real/destructive actions if simulation mode is active
    if settings.SIMULATION_MODE and action_type == ActionType.RESTART_CONTAINER.value:
        sim_msg = "Restart operations are blocked in simulation mode."
        agent_metrics.record_rejected(reason="simulation_mode_blocked")
        audit_logger.record_event(
            event_type="simulation_block",
            action_id=action_req.action_id,
            target_container=action_req.target_container,
            action_type=action_req.action_type,
            status=ActionStatus.REJECTED.value,
            exit_code=2,
            duration_ms=0,
            evidence_hash=hashlib.sha256(b"blocked_in_simulation_mode").hexdigest(),
            details=sim_msg,
            correlation_id=action_req.correlation_id,
            client_ip=client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=sim_msg,
        )

    stdout_output = ""
    stderr_output = ""
    exit_code = 0
    action_status = ActionStatus.SUCCESS
    is_mocked = False

    try:
        if action_type == ActionType.RESTART_CONTAINER.value:
            timeout = sanitized_params.get("timeout_seconds", 15)
            restart_res = docker_client.restart_container(
                container_name=action_req.target_container,
                timeout_seconds=timeout,
            )
            stdout_output = restart_res.get("stdout", "")
            stderr_output = restart_res.get("stderr", "")
            exit_code = restart_res.get("exit_code", 0)
            is_mocked = restart_res.get("is_mocked", False)
            if exit_code != 0:
                action_status = ActionStatus.FAILED

        elif action_type in (
            ActionType.INSPECT_CONTAINER.value,
            ActionType.GET_CONTAINER_STATE.value,
            ActionType.GET_CONTAINER_HEALTH.value,
        ):
            status_res = docker_client.inspect_container(action_req.target_container)
            stdout_output = (
                f"Container: {status_res.container_name} | State: {status_res.state} | "
                f"Health: {status_res.health} | Restarts: {status_res.restart_count} | "
                f"Uptime: {status_res.uptime_seconds}s"
            )
            is_mocked = status_res.is_mocked

        elif action_type == ActionType.VERIFY_CONTAINER_HEALTH.value:
            endpoint = sanitized_params.get("health_endpoint", "/health")
            expected_st = sanitized_params.get("expected_status", 200)
            verified, probe_code, probe_msg, probe_dur = await health_verifier.verify_application_health(
                target_host=action_req.target_container,
                health_path=endpoint,
                expected_status=expected_st,
            )
            stdout_output = probe_msg
            if not verified:
                action_status = ActionStatus.FAILED
                exit_code = 1
                stderr_output = f"Application health verification failed: status {probe_code}"

    except FileNotFoundError as fnf:
        action_status = ActionStatus.FAILED
        exit_code = 1
        stderr_output = str(fnf)
    except Exception as exc:
        action_status = ActionStatus.FAILED
        exit_code = 1
        stderr_output = f"Execution exception: {str(exc)}"

    duration_ms = int((time.time() - start_time) * 1000)

    # 6. Generate SHA-256 evidence receipt hash
    evidence_raw = f"{action_req.action_id}:{action_req.target_container}:{action_type}:{action_status.value}:{exit_code}:{stdout_output}:{duration_ms}"
    evidence_hash = hashlib.sha256(evidence_raw.encode("utf-8")).hexdigest()

    # 7. Record Metrics and Immutable Audit Event
    agent_metrics.record_execution(
        success=(action_status == ActionStatus.SUCCESS and exit_code == 0),
        duration_ms=duration_ms,
    )
    audit_logger.record_event(
        event_type="action_executed",
        action_id=action_req.action_id,
        target_container=action_req.target_container,
        action_type=action_req.action_type,
        status=action_status.value,
        exit_code=exit_code,
        duration_ms=duration_ms,
        evidence_hash=evidence_hash,
        details=f"Executed with exit code {exit_code}.",
        correlation_id=action_req.correlation_id,
        client_ip=client_ip,
        is_mocked=is_mocked,
    )

    return ActionExecutionResponse(
        action_id=action_req.action_id,
        target_container=action_req.target_container,
        action_type=action_req.action_type,
        status=action_status,
        exit_code=exit_code,
        duration_ms=duration_ms,
        stdout=stdout_output,
        stderr=stderr_output,
        evidence_receipt_hash=evidence_hash,
        executed_at=datetime.now(timezone.utc),
        correlation_id=action_req.correlation_id,
        is_mocked=is_mocked,
    )


@app.on_event("startup")
def startup_security_validation():
    """Validates configuration parameters and secret strength on server startup."""
    settings.validate_security()


@app.get("/api/v1/audit/logs", tags=["Audit"])
def get_audit_logs(
    limit: int = 50,
    authorization: Optional[str] = Header(None),
):
    """Returns recent execution audit logs from bounded buffer."""
    if settings.REQUIRE_AUTH_FOR_AUDIT:
        expected = f"Bearer {settings.AGENT_SECRET_KEY}"
        if not authorization or not hmac.compare_digest(authorization.strip(), expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: valid Bearer token matching AGENT_SECRET_KEY is required.",
            )
    return {"logs": audit_logger.get_recent_logs(limit=limit)}
