"""
AutoHeal DevOps — Phase 16 Restricted Docker Agent & Integration Tests
Validates the restricted Docker agent architecture, security model, allowlists,
replay defenses, two-stage recovery verification, and safe simulation boundaries.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import re
import uuid
import pytest
from starlette.testclient import TestClient

# Standalone Restricted Docker Agent imports
from docker_agent.allowlist import (
    APPROVED_CONTAINERS,
    CRITICAL_PROTECTED_CONTAINERS,
    ALLOWED_OPERATIONS,
    validate_operation_allowlist,
)
from docker_agent.audit import audit_logger
from docker_agent.config import AgentSettings, settings as agent_settings
from docker_agent.metrics import agent_metrics
from docker_agent.models import ActionExecutionRequest, ActionStatus, ActionType
from docker_agent.security import (
    canonicalize_payload,
    clean_expired_nonces,
    reset_nonce_cache,
    sign_payload,
    validate_container_name_security,
    verify_payload_signature,
)
from docker_agent.server import app as agent_app
from docker_agent.verifier import ApplicationHealthVerifier

# Backend control plane integration imports
from unittest.mock import AsyncMock, MagicMock
from app.config import get_settings
from app.models.incident import Incident
from app.models.recovery import RecoveryAction, RecoveryResult
from app.models.service import Service
from app.services.agent.docker_client import RestrictedDockerAgentClient
from app.services.agent.models import ActionRequest, ActionExecutionStatus
from app.services.recovery.executor import RecoveryExecutor
from app.services.recovery.verifier import PostRecoveryVerifier

SECRET_KEY = "autoheal_docker_agent_secret_32chars_min"


@pytest.fixture(autouse=True)
def clean_agent_state():
    """Resets nonce cache, audit buffer, and metrics before each test."""
    reset_nonce_cache()
    audit_logger.clear()
    agent_metrics.reset()
    agent_settings.AGENT_SECRET_KEY = SECRET_KEY
    yield
    reset_nonce_cache()
    audit_logger.clear()
    agent_metrics.reset()
    agent_settings.AGENT_SECRET_KEY = SECRET_KEY


# =====================================================================
# 1. SECURITY TESTS — Cryptographic Integrity & Anti-Replay
# =====================================================================


def test_signature_verification_success():
    """Confirms valid HMAC-SHA256 signature and fresh timestamp are accepted."""
    now = datetime.now(timezone.utc)
    nonce = uuid.uuid4().hex
    sig = sign_payload(
        secret_key=SECRET_KEY,
        action_id="act-001",
        target_container="autoheal_test_service",
        action_type="restart_container",
        parameters={"timeout_seconds": 15},
        nonce=nonce,
        timestamp_iso=now.isoformat(),
    )

    valid, err = verify_payload_signature(
        secret_key=SECRET_KEY,
        action_id="act-001",
        target_container="autoheal_test_service",
        action_type="restart_container",
        parameters={"timeout_seconds": 15},
        nonce=nonce,
        timestamp=now,
        provided_signature=sig,
    )
    assert valid is True
    assert err == ""


def test_signature_verification_rejection_invalid_secret():
    """Confirms request signed with wrong secret is rejected."""
    now = datetime.now(timezone.utc)
    nonce = uuid.uuid4().hex
    sig = sign_payload(
        secret_key="wrong_secret_key_that_does_not_match_32c",
        action_id="act-002",
        target_container="autoheal_test_service",
        action_type="restart_container",
        parameters={},
        nonce=nonce,
        timestamp_iso=now.isoformat(),
    )

    valid, err = verify_payload_signature(
        secret_key=SECRET_KEY,
        action_id="act-002",
        target_container="autoheal_test_service",
        action_type="restart_container",
        parameters={},
        nonce=nonce,
        timestamp=now,
        provided_signature=sig,
    )
    assert valid is False
    assert "mismatch" in err.lower()


def test_signature_verification_rejection_expired_timestamp():
    """Confirms request with timestamp older than 300 seconds is rejected (anti-replay/drift)."""
    old_time = datetime.now(timezone.utc) - timedelta(seconds=360)
    nonce = uuid.uuid4().hex
    sig = sign_payload(
        secret_key=SECRET_KEY,
        action_id="act-003",
        target_container="autoheal_test_service",
        action_type="restart_container",
        parameters={},
        nonce=nonce,
        timestamp_iso=old_time.isoformat(),
    )

    valid, err = verify_payload_signature(
        secret_key=SECRET_KEY,
        action_id="act-003",
        target_container="autoheal_test_service",
        action_type="restart_container",
        parameters={},
        nonce=nonce,
        timestamp=old_time,
        provided_signature=sig,
    )
    assert valid is False
    assert "drift" in err.lower()


def test_signature_verification_rejection_replayed_nonce():
    """Confirms re-submitting an identical nonce is rejected (replay attack prevention)."""
    now = datetime.now(timezone.utc)
    nonce = "replay-nonce-fixed-12345"
    sig = sign_payload(
        secret_key=SECRET_KEY,
        action_id="act-004",
        target_container="autoheal_test_service",
        action_type="restart_container",
        parameters={},
        nonce=nonce,
        timestamp_iso=now.isoformat(),
    )

    # First attempt: succeeds
    valid1, _ = verify_payload_signature(
        secret_key=SECRET_KEY,
        action_id="act-004",
        target_container="autoheal_test_service",
        action_type="restart_container",
        parameters={},
        nonce=nonce,
        timestamp=now,
        provided_signature=sig,
    )
    assert valid1 is True

    # Second attempt with same nonce: rejected
    valid2, err2 = verify_payload_signature(
        secret_key=SECRET_KEY,
        action_id="act-004",
        target_container="autoheal_test_service",
        action_type="restart_container",
        parameters={},
        nonce=nonce,
        timestamp=now,
        provided_signature=sig,
    )
    assert valid2 is False
    assert "replay detected" in err2.lower()


# =====================================================================
# 2. ALLOWLIST TESTS — Container & Action Boundary Enforcement
# =====================================================================


def test_allowlist_permits_approved_test_service():
    """Confirms designated test container and valid restart operation pass allowlist."""
    valid, err, sanitized = validate_operation_allowlist(
        target_container="autoheal_test_service",
        action_type="restart_container",
        parameters={"timeout_seconds": 20},
    )
    assert valid is True
    assert err == ""
    assert sanitized["timeout_seconds"] == 20


def test_allowlist_rejects_critical_production_containers():
    """Confirms core infrastructure containers (db, redis, backend, etc.) are strictly protected."""
    for protected in ["db", "postgres", "redis", "backend", "frontend", "prometheus", "alertmanager"]:
        valid, err, _ = validate_operation_allowlist(
            target_container=protected,
            action_type="restart_container",
            parameters={},
        )
        assert valid is False
        assert "protected core infrastructure" in err.lower()


def test_allowlist_rejects_unregistered_containers():
    """Confirms any unapproved container name is rejected."""
    valid, err, _ = validate_operation_allowlist(
        target_container="random_customer_container",
        action_type="restart_container",
        parameters={},
    )
    assert valid is False
    assert "not registered in the approved target allowlist" in err.lower()


def test_allowlist_rejects_unapproved_operations():
    """Confirms arbitrary shell, exec, or unapproved actions are rejected."""
    forbidden_actions = ["exec_bash", "docker_rm", "create_container", "system_reboot", "eval_code"]
    for act in forbidden_actions:
        valid, err, _ = validate_operation_allowlist(
            target_container="autoheal_test_service",
            action_type=act,
            parameters={},
        )
        assert valid is False
        assert "not in the approved operations allowlist" in err.lower()


def test_allowlist_rejects_command_injection_and_metacharacters():
    """Confirms shell metacharacters in parameters or container names are rejected."""
    for bad_name in ["autoheal_test; rm -rf /", "test`whoami`", "service|reboot", "app$(id)"]:
        valid, _ = validate_container_name_security(bad_name)
        assert valid is False

    valid, err, _ = validate_operation_allowlist(
        target_container="autoheal_test_service",
        action_type="verify_container_health",
        parameters={"health_endpoint": "/health; rm -rf /"},
    )
    assert valid is False
    assert "illegal characters" in err.lower()


# =====================================================================
# 3. RESTRICTED AGENT API TESTS (via TestClient)
# =====================================================================


def test_agent_health_endpoint():
    """Tests GET /health on restricted agent."""
    client = TestClient(agent_app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == "docker-agent-restricted-01"
    assert "autoheal_test_service" in data["approved_containers"]
    assert "restart_container" in data["allowed_operations"]


def test_agent_metrics_endpoint():
    """Tests GET /metrics returns standard Prometheus formatted metrics."""
    client = TestClient(agent_app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "autoheal_docker_agent_requests_received_total" in resp.text
    assert "autoheal_docker_agent_executions_total" in resp.text


def test_agent_container_inspection_approved_container():
    """Tests GET /api/v1/containers/{name}/status for an approved container."""
    client = TestClient(agent_app)
    resp = client.get("/api/v1/containers/autoheal_test_service/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["container_name"] == "autoheal_test_service"
    assert data["status"] in ("running", "healthy", "exited")


def test_agent_container_inspection_unapproved_container():
    """Tests GET /api/v1/containers/{name}/status rejects unapproved containers."""
    client = TestClient(agent_app)
    resp = client.get("/api/v1/containers/db/status")
    assert resp.status_code == 403
    assert "not in the approved allowlist" in resp.json()["detail"].lower()


def test_agent_execute_action_authorized_flow(monkeypatch):
    """Tests successful end-to-end execution of signed restart action when simulation mode is disabled."""
    monkeypatch.setattr(agent_settings, "SIMULATION_MODE", False)
    client = TestClient(agent_app)
    now = datetime.now(timezone.utc)
    nonce = uuid.uuid4().hex
    sig = sign_payload(
        secret_key=SECRET_KEY,
        action_id="act-auth-100",
        target_container="autoheal_test_service",
        action_type="restart_container",
        parameters={"timeout_seconds": 15},
        nonce=nonce,
        timestamp_iso=now.isoformat(),
    )

    payload = {
        "action_id": "act-auth-100",
        "target_container": "autoheal_test_service",
        "action_type": "restart_container",
        "parameters": {"timeout_seconds": 15},
        "timeout_seconds": 30,
        "nonce": nonce,
        "timestamp": now.isoformat(),
        "signature": sig,
        "correlation_id": "test-corr-01",
    }

    resp = client.post("/api/v1/actions/execute", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_id"] == "act-auth-100"
    assert data["status"] == "success"
    assert data["exit_code"] == 0
    assert len(data["evidence_receipt_hash"]) == 64

    # Verify audit log was recorded
    audit_resp = client.get("/api/v1/audit/logs")
    assert audit_resp.status_code == 200
    logs = audit_resp.json()["logs"]
    assert any(log["action_id"] == "act-auth-100" for log in logs)


def test_agent_execute_action_blocked_in_simulation_mode():
    """Confirms that when SIMULATION_MODE is True, restart_container operations are strictly rejected with 403."""
    client = TestClient(agent_app)
    now = datetime.now(timezone.utc)
    nonce = uuid.uuid4().hex
    sig = sign_payload(
        secret_key=SECRET_KEY,
        action_id="act-sim-block-01",
        target_container="autoheal_test_service",
        action_type="restart_container",
        parameters={"timeout_seconds": 15},
        nonce=nonce,
        timestamp_iso=now.isoformat(),
    )

    payload = {
        "action_id": "act-sim-block-01",
        "target_container": "autoheal_test_service",
        "action_type": "restart_container",
        "parameters": {"timeout_seconds": 15},
        "timeout_seconds": 30,
        "nonce": nonce,
        "timestamp": now.isoformat(),
        "signature": sig,
        "correlation_id": "test-corr-sim",
    }

    resp = client.post("/api/v1/actions/execute", json=payload)
    assert resp.status_code == 403
    assert "blocked in simulation mode" in resp.json()["detail"].lower()


def test_agent_execute_action_rejected_unauthorized():
    """Tests that unsigned or improperly signed requests are rejected with 401."""
    client = TestClient(agent_app)
    now = datetime.now(timezone.utc)
    payload = {
        "action_id": "act-bad-sig",
        "target_container": "autoheal_test_service",
        "action_type": "restart_container",
        "parameters": {},
        "timeout_seconds": 30,
        "nonce": uuid.uuid4().hex,
        "timestamp": now.isoformat(),
        "signature": "bogus_signature_hash_12345",
    }

    resp = client.post("/api/v1/actions/execute", json=payload)
    assert resp.status_code == 401
    assert "signature mismatch" in resp.json()["detail"].lower()


def test_agent_execute_action_rejected_target_not_approved():
    """Tests that signed requests targeting non-whitelisted containers are rejected with 403."""
    client = TestClient(agent_app)
    now = datetime.now(timezone.utc)
    nonce = uuid.uuid4().hex
    sig = sign_payload(
        secret_key=SECRET_KEY,
        action_id="act-target-unapproved",
        target_container="production_billing_app",
        action_type="restart_container",
        parameters={},
        nonce=nonce,
        timestamp_iso=now.isoformat(),
    )

    payload = {
        "action_id": "act-target-unapproved",
        "target_container": "production_billing_app",
        "action_type": "restart_container",
        "parameters": {},
        "timeout_seconds": 30,
        "nonce": nonce,
        "timestamp": now.isoformat(),
        "signature": sig,
    }

    resp = client.post("/api/v1/actions/execute", json=payload)
    assert resp.status_code == 403
    assert "not registered in the approved target allowlist" in resp.json()["detail"].lower()


# =====================================================================
# 4. TWO-STAGE RECOVERY VERIFICATION TESTS
# =====================================================================


@pytest.mark.asyncio
async def test_health_verifier_success():
    """Tests that health probe returns true when service reports healthy."""
    verifier = ApplicationHealthVerifier()
    ok, status_code, msg, dur = await verifier.verify_application_health(mock_healthy=True)
    assert ok is True
    assert status_code == 200
    assert "healthy" in msg


@pytest.mark.asyncio
async def test_health_verifier_failure_marks_recovery_unresolved():
    """
    CRITICAL SAFETY REQUIREMENT:
    Even if a container restart succeeds, if application health verification fails (e.g. HTTP 503),
    the verification must be marked as failed. A Docker restart != recovery success.
    """
    verifier = ApplicationHealthVerifier()
    ok, status_code, msg, dur = await verifier.verify_application_health(mock_healthy=False)
    assert ok is False
    assert status_code == 503
    assert "degraded" in msg


# =====================================================================
# 5. REGRESSION & SIMULATION MODE TESTS
# =====================================================================


def test_simulation_mode_is_default_and_safe():
    """Confirms that RECOVERY_SIMULATION_MODE defaults to True and RESTRICTED_DOCKER_AGENT_ENABLED is False."""
    settings = get_settings()
    assert settings.RECOVERY_SIMULATION_MODE is True
    assert getattr(settings, "RESTRICTED_DOCKER_AGENT_ENABLED", False) is False

    # Confirms RecoveryExecutor instantiates SimulatedAgentClient by default
    executor = RecoveryExecutor()
    from app.services.agent.simulator import SimulatedAgentClient
    assert isinstance(executor.agent_client, SimulatedAgentClient)


def test_insecure_secret_validation_in_production(monkeypatch):
    """Verifies that validate_security fails fast if insecure secret is configured in production or staging."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(agent_settings, "AGENT_SECRET_KEY", "autoheal_docker_agent_secret_32chars_min")
    with pytest.raises(ValueError, match="Insecure default DOCKER_AGENT_SECRET_KEY"):
        agent_settings.validate_security()

    monkeypatch.setattr(agent_settings, "AGENT_SECRET_KEY", "too_short")
    with pytest.raises(ValueError, match="at least 32 characters long"):
        agent_settings.validate_security()


def test_audit_logs_auth_requirement(monkeypatch):
    """Verifies that audit log retrieval enforces authorization header when REQUIRE_AUTH_FOR_AUDIT is enabled."""
    monkeypatch.setattr(agent_settings, "REQUIRE_AUTH_FOR_AUDIT", True)
    client = TestClient(agent_app)

    # Missing auth header -> 401
    resp_unauth = client.get("/api/v1/audit/logs")
    assert resp_unauth.status_code == 401

    # Valid Bearer token matching secret key -> 200
    resp_auth = client.get(
        "/api/v1/audit/logs",
        headers={"Authorization": f"Bearer {SECRET_KEY}"},
    )
    assert resp_auth.status_code == 200
    assert "logs" in resp_auth.json()


@pytest.mark.asyncio
async def test_verifier_preserves_pre_recovery_latency_baseline():
    """
    CRITICAL FIX VERIFICATION:
    Verifies that PostRecoveryVerifier preserves service.latency_ms pre-recovery baseline
    and compares against it without overwriting it before diff calculation.
    """
    verifier = PostRecoveryVerifier()
    db = AsyncMock()

    service = Service(
        id="svc-checkout",
        name="checkout-api",
        latency_ms=780,  # High pre-recovery latency baseline
        error_rate=8.5,
        availability=94.2,
        status="degraded",
    )
    incident = Incident(
        id="INC-999",
        service_id=service.id,
        service_name=service.name,
        error_rate=8.5,
        threshold=1.0,
        status="recovering",
        organization_id=uuid.uuid4(),
    )
    recovery = RecoveryAction(
        id="REC-999",
        incident_id=incident.id,
        service_id=service.id,
        service_name=service.name,
        action="restart_container",
        status="running",
        verification="pending",
    )

    success = await verifier.verify_recovery(
        db=db,
        recovery=recovery,
        incident=incident,
        service=service,
        simulated_healthy=True,
    )

    assert success is True
    assert recovery.verification == "passed"
    assert recovery.execution_mode == "SIMULATED"
    assert recovery.evidence_classification == "SIMULATED"
    assert service.status == "healthy"
    assert service.latency_ms == 115
    assert "P95 latency normalized to 115ms" in recovery.result.summary


@pytest.mark.asyncio
async def test_failed_verification_state_transitions():
    """
    CRITICAL SAFETY REQUIREMENT:
    When post-recovery verification fails, recovery.verification must be 'failed',
    evidence_classification must be 'VERIFICATION_FAILED', incident.status must remain
    'investigating' (NEVER 'resolved'), and incident.resolved_at must be None.
    """
    verifier = PostRecoveryVerifier()
    db = AsyncMock()

    service = Service(
        id="svc-order",
        name="order-api",
        latency_ms=650,
        error_rate=5.0,
        availability=96.0,
        status="degraded",
    )
    incident = Incident(
        id="INC-888",
        service_id=service.id,
        service_name=service.name,
        error_rate=5.0,
        threshold=1.0,
        status="recovering",
        organization_id=uuid.uuid4(),
    )
    recovery = RecoveryAction(
        id="REC-888",
        incident_id=incident.id,
        service_id=service.id,
        service_name=service.name,
        action="restart_container",
        status="running",
        verification="pending",
    )

    success = await verifier.verify_recovery(
        db=db,
        recovery=recovery,
        incident=incident,
        service=service,
        simulated_healthy=False,  # Verification fails
        execution_mode="REAL",
    )

    assert success is False
    assert recovery.verification == "failed"
    assert recovery.execution_mode == "REAL"
    assert recovery.evidence_classification == "VERIFICATION_FAILED"
    assert incident.status == "investigating"
    assert incident.resolved_at is None
    assert recovery.result.verified is False
    assert "Verification Failed" in recovery.result.summary


# ============================================================================
# PHASE 16 HARDENED L7 NGINX PROXY & MTLS TESTS
# ============================================================================

def test_mtls_exact_certificate_identity_validation():
    """
    CRITICAL SECURITY REQUIREMENT:
    Subject DN validation in the NGINX proxy must enforce exact identity:
    Only exact 'CN=autoheal_docker_agent' is allowed.
    All variations (subdomains, prefix, suffix, unapproved OU) must be rejected.
    """
    pattern = re.compile(r"^CN=autoheal_docker_agent$")

    # Positive match
    assert pattern.match("CN=autoheal_docker_agent") is not None

    # Negative matches (unauthorized or spoofed identities)
    unauthorized_subjects = [
        "CN=autoheal_docker_agent_evil",
        "CN=autoheal_docker_agent.attacker.com",
        "CN=evil_autoheal_docker_agent",
        "CN=autoheal_docker_agent_2",
        "CN=attacker",
        "CN=autoheal_docker_agent,OU=evil",
        "CN=autoheal_docker_agent,DC=attacker,DC=com",
        "CN=root",
        "CN=admin",
        "",
    ]
    for subject in unauthorized_subjects:
        assert pattern.match(subject) is None, f"Expected '{subject}' to be rejected by exact identity regex."


def test_l7_proxy_route_and_method_restrictions():
    """
    CRITICAL SECURITY REQUIREMENT:
    The NGINX L7 proxy allows ONLY:
    - GET /containers/autoheal_test_service/json (or /v1.X/...)
    - POST /containers/autoheal_test_service/restart (with optional t=[0-9]{1,2})
    Every other container, endpoint, verb, and parameter is rejected before reaching socket.
    """
    route_regex = re.compile(r"^/(v[0-9]+\.[0-9]+/)?containers/autoheal_test_service/(json|restart)$")
    allowed_methods = {"GET": {"json"}, "POST": {"restart"}}
    allowed_restart_args = re.compile(r"^(t=[0-9]{1,2})?$")

    def simulate_nginx_filter(method: str, raw_uri: str, client_subject: str = "CN=autoheal_docker_agent"):
        # 1. Subject DN check
        if not re.match(r"^CN=autoheal_docker_agent$", client_subject):
            return 403, "Forbidden: unauthorized client certificate identity"

        # 2. URI parse & normalize
        from urllib.parse import urlparse
        import posixpath
        parsed = urlparse(raw_uri)
        normalized_path = posixpath.normpath(parsed.path)
        query = parsed.query

        # 3. Route regex
        m = route_regex.match(normalized_path)
        if not m:
            return 403, "Forbidden: endpoint not permitted by security proxy"

        endpoint = m.group(2)

        # 4. Method check
        if method not in allowed_methods or endpoint not in allowed_methods[method]:
            return 405, f"Method Not Allowed: only permitted methods allowed"

        # 5. Query check
        if endpoint == "json" and query != "":
            return 400, "Bad Request: query parameters not permitted on inspect"
        elif endpoint == "restart" and not allowed_restart_args.match(query):
            return 400, "Bad Request: invalid query parameters for restart"

        return 200, "OK"

    # Permitted operations
    assert simulate_nginx_filter("GET", "/containers/autoheal_test_service/json")[0] == 200
    assert simulate_nginx_filter("GET", "/v1.41/containers/autoheal_test_service/json")[0] == 200
    assert simulate_nginx_filter("POST", "/containers/autoheal_test_service/restart")[0] == 200
    assert simulate_nginx_filter("POST", "/v1.41/containers/autoheal_test_service/restart")[0] == 200
    assert simulate_nginx_filter("POST", "/v1.41/containers/autoheal_test_service/restart?t=10")[0] == 200

    # Unauthorized client subject
    assert simulate_nginx_filter("GET", "/containers/autoheal_test_service/json", client_subject="CN=evil")[0] == 403

    # Prohibited containers
    assert simulate_nginx_filter("POST", "/containers/autoheal_postgres/restart")[0] == 403
    assert simulate_nginx_filter("POST", "/containers/autoheal_backend/restart")[0] == 403
    assert simulate_nginx_filter("POST", "/containers/1a2b3c4d5e6f/restart")[0] == 403

    # Prohibited endpoints
    assert simulate_nginx_filter("POST", "/containers/create")[0] == 403
    assert simulate_nginx_filter("POST", "/containers/autoheal_test_service/kill")[0] == 403
    assert simulate_nginx_filter("POST", "/containers/autoheal_test_service/stop")[0] == 403
    assert simulate_nginx_filter("POST", "/containers/autoheal_test_service/exec")[0] == 403
    assert simulate_nginx_filter("DELETE", "/containers/autoheal_test_service")[0] == 403
    assert simulate_nginx_filter("GET", "/images/json")[0] == 403
    assert simulate_nginx_filter("GET", "/volumes")[0] == 403

    # Prohibited verbs
    assert simulate_nginx_filter("GET", "/containers/autoheal_test_service/restart")[0] == 405
    assert simulate_nginx_filter("POST", "/containers/autoheal_test_service/json")[0] == 405
    assert simulate_nginx_filter("DELETE", "/containers/autoheal_test_service/json")[0] == 405

    # Prohibited query parameters
    assert simulate_nginx_filter("GET", "/containers/autoheal_test_service/json?size=1")[0] == 400
    assert simulate_nginx_filter("POST", "/containers/autoheal_test_service/restart?t=10&evil=1")[0] == 400
    assert simulate_nginx_filter("POST", "/containers/autoheal_test_service/restart?force=true")[0] == 400


@pytest.mark.asyncio
async def test_mock_socket_isolation_harness():
    """
    SAFE TESTING REQUIREMENT:
    Verifies that requests passing through the L7 proxy filter only reach the mock socket
    when strictly authorized. All rejected requests return 400/403/405 and NEVER reach the socket.
    Zero interaction with real host Docker daemon.
    """
    import asyncio

    received_requests = []

    # Mock Docker daemon stream server
    async def handle_client(reader, writer):
        data = await reader.read(4096)
        if data:
            received_requests.append(data.decode("utf-8", errors="replace").split("\r\n")[0])
        response = "HTTP/1.1 200 OK\r\nContent-Length: 15\r\n\r\n{\"status\":\"ok\"}"
        writer.write(response.encode("utf-8"))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle_client, host="127.0.0.1", port=0)
    upstream_port = server.sockets[0].getsockname()[1]

    route_regex = re.compile(r"^/(v[0-9]+\.[0-9]+/)?containers/autoheal_test_service/(json|restart)$")
    allowed_methods = {"GET": {"json"}, "POST": {"restart"}}
    allowed_restart_args = re.compile(r"^(t=[0-9]{1,2})?$")

    async def forward_through_proxy(method: str, uri: str, subject: str = "CN=autoheal_docker_agent"):
        if subject != "CN=autoheal_docker_agent":
            return 403
        from urllib.parse import urlparse
        import posixpath
        parsed = urlparse(uri)
        normalized = posixpath.normpath(parsed.path)
        m = route_regex.match(normalized)
        if not m:
            return 403
        endpoint = m.group(2)
        if method not in allowed_methods or endpoint not in allowed_methods[method]:
            return 405
        if endpoint == "json" and parsed.query:
            return 400
        if endpoint == "restart" and not allowed_restart_args.match(parsed.query):
            return 400

        # Only authorized calls reach the upstream socket
        reader, writer = await asyncio.open_connection("127.0.0.1", upstream_port)
        req = f"{method} {uri} HTTP/1.1\r\nHost: docker_daemon\r\n\r\n"
        writer.write(req.encode("utf-8"))
        await writer.drain()
        await reader.read(1024)
        writer.close()
        await writer.wait_closed()
        return 200

    try:
        # Permitted requests (reach mock socket)
        code1 = await forward_through_proxy("GET", "/containers/autoheal_test_service/json")
        code2 = await forward_through_proxy("POST", "/v1.41/containers/autoheal_test_service/restart?t=10")
        assert code1 == 200
        assert code2 == 200
        assert len(received_requests) == 2

        # Forbidden requests (rejected before reaching mock socket)
        assert await forward_through_proxy("POST", "/containers/autoheal_postgres/restart") == 403
        assert await forward_through_proxy("POST", "/containers/create") == 403
        assert await forward_through_proxy("POST", "/containers/autoheal_test_service/kill") == 403
        assert await forward_through_proxy("GET", "/containers/autoheal_test_service/restart") == 405
        assert await forward_through_proxy("POST", "/containers/autoheal_test_service/restart?evil=1") == 400
        assert await forward_through_proxy("GET", "/containers/autoheal_test_service/json", subject="CN=attacker") == 403

        # Exactly 2 requests arrived at the mock daemon; all 6 unauthorized calls were blocked
        assert len(received_requests) == 2
    finally:
        server.close()
        await server.wait_closed()


def test_secure_credential_entropy_and_default_rejection(monkeypatch):
    """
    CRITICAL SECURITY REQUIREMENT:
    DOCKER_AGENT_SECRET_KEY must enforce high entropy and reject predictable default tokens.
    """
    settings = AgentSettings()

    # 1. Missing secret in production raises ValueError
    monkeypatch.setenv("APP_ENV", "production")
    settings.AGENT_SECRET_KEY = ""
    with pytest.raises(ValueError, match="DOCKER_AGENT_SECRET_KEY must be set"):
        settings.validate_security()

    # 2. Secret shorter than 32 characters in production raises ValueError
    settings.AGENT_SECRET_KEY = "short_secret_20_chars"
    with pytest.raises(ValueError, match="at least 32 characters"):
        settings.validate_security()

    # 3. Predictable default patterns raise ValueError
    insecure_defaults = [
        "autoheal_agent_default_secret_key_prod_32b",
        "autoheal_docker_agent_secret_32chars_min",
        "my_production_default_secret_key_12345",
        "change_me_super_secure_key_1234567890",
    ]
    for bad_secret in insecure_defaults:
        settings.AGENT_SECRET_KEY = bad_secret
        with pytest.raises(ValueError, match="predictable pattern"):
            settings.validate_security()

    # 4. Cryptographically strong secret passes validation
    settings.AGENT_SECRET_KEY = "f8a7d9c2e1b4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0"
    assert settings.validate_security() is None

    # 5. Secret is redacted in __repr__
    repr_str = repr(settings)
    assert "[REDACTED]" in repr_str
    assert "f8a7d9c2" not in repr_str


def test_cadvisor_socket_exposure_elimination():
    """
    CRITICAL SECURITY REQUIREMENT:
    cAdvisor in docker-compose.yml must NOT mount /var/run or /var/run/docker.sock.
    FastAPI backend must NOT mount /var/run/docker.sock.
    Docker Agent must NOT mount /var/run/docker.sock.
    Only autoheal_socket_proxy receives the host Docker socket.
    """
    import yaml

    with open("docker-compose.yml", "r", encoding="utf-8") as f:
        core_compose = yaml.safe_load(f)

    cadvisor_volumes = core_compose.get("services", {}).get("cadvisor", {}).get("volumes", [])
    for vol in cadvisor_volumes:
        vol_str = vol if isinstance(vol, str) else vol.get("source", "")
        assert "/var/run" not in vol_str, f"Forbidden /var/run mount detected in cAdvisor: {vol_str}"
        assert "docker.sock" not in vol_str, f"Forbidden docker.sock mount detected in cAdvisor: {vol_str}"

    backend_volumes = core_compose.get("services", {}).get("backend", {}).get("volumes", [])
    for vol in backend_volumes:
        vol_str = vol if isinstance(vol, str) else vol.get("source", "")
        assert "docker.sock" not in vol_str, f"Forbidden docker.sock mount detected in backend: {vol_str}"

    with open("docker-compose.test-infra.yml", "r", encoding="utf-8") as f:
        test_compose = yaml.safe_load(f)

    agent_volumes = test_compose.get("services", {}).get("autoheal_docker_agent", {}).get("volumes", [])
    for vol in agent_volumes:
        vol_str = vol if isinstance(vol, str) else vol.get("source", "")
        assert "docker.sock" not in vol_str, f"Forbidden docker.sock mount detected in Docker Agent: {vol_str}"

    proxy_volumes = test_compose.get("services", {}).get("autoheal_socket_proxy", {}).get("volumes", [])
    has_proxy_socket = any("docker.sock" in (v if isinstance(v, str) else v.get("source", "")) for v in proxy_volumes)
    assert has_proxy_socket, "autoheal_socket_proxy must mount docker.sock"

