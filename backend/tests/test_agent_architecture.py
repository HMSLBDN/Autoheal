"""
AutoHeal DevOps — Restricted Infrastructure Agent Architecture Tests
Verifies cryptographic envelope signing, nonce replay prevention, allowlist enforcement,
and safe simulated execution receipts.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import uuid
import pytest

from app.services.agent import (
    ActionRequest,
    ActionResult,
    AgentHeartbeat,
    AgentRegistration,
    ALLOWED_AGENT_ACTIONS,
    InfrastructureAgentClient,
    SimulatedAgentClient,
    sign_payload,
    validate_agent_action,
    verify_payload_signature,
)
from app.services.agent.models import ActionExecutionStatus, AgentStatus


@pytest.mark.asyncio
async def test_agent_registration_and_heartbeat():
    client = SimulatedAgentClient(agent_id="test-agent-01")
    reg = AgentRegistration(
        agent_id="test-agent-01",
        hostname="node-worker-01.internal",
        ip_address="10.0.1.42",
        supported_actions=list(ALLOWED_AGENT_ACTIONS),
        public_key_fingerprint=hashlib.sha256(b"node-worker-01-pubkey").hexdigest(),
    )
    registered = await client.register(reg)
    assert registered is True

    heartbeat = await client.get_heartbeat()
    assert heartbeat.agent_id == "test-agent-01"
    assert heartbeat.status == AgentStatus.ONLINE
    assert heartbeat.cpu_percent >= 0.0


def test_agent_allowlist_validation_success():
    # Permitted: restart_service
    valid, err, sanitized = validate_agent_action("restart_service", {"grace_period_seconds": 15})
    assert valid is True
    assert err == ""
    assert sanitized["grace_period_seconds"] == 15

    # Permitted: scale_service
    valid, err, sanitized = validate_agent_action("scale_service", {"replicas": 4})
    assert valid is True
    assert sanitized["replicas"] == 4


def test_agent_allowlist_rejection_forbidden_actions():
    # Forbidden: arbitrary shell command
    valid, err, _ = validate_agent_action("execute_bash", {"cmd": "rm -rf /"})
    assert valid is False
    assert "not permitted" in err

    # Forbidden: python code execution
    valid, err, _ = validate_agent_action("eval_python", {"code": "import os; os.system('ls')"})
    assert valid is False


def test_agent_allowlist_parameter_bounds_and_injection():
    # Out of range replica count (>10)
    valid, err, _ = validate_agent_action("scale_service", {"replicas": 999})
    assert valid is False
    assert "<= 10" in err

    # Shell metacharacter injection attempt
    valid, err, _ = validate_agent_action("rollback_deployment", {"target_revision": "v1.2.0; rm -rf /"})
    assert valid is False
    assert "Illegal characters" in err


def test_cryptographic_signature_and_nonce_replay():
    secret = "test_shared_agent_secret_key_32c"
    action_id = "act-12345"
    service_id = "svc-67890"
    action_type = "restart_service"
    params = {"grace_period_seconds": 10}
    nonce = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    sig = sign_payload(secret, action_id, service_id, action_type, params, nonce, now_iso)
    assert len(sig) == 64

    # 1. First verification succeeds
    valid = verify_payload_signature(secret, action_id, service_id, action_type, params, nonce, now, sig)
    assert valid is True

    # 2. Replay with the exact same nonce must fail
    replay_valid = verify_payload_signature(secret, action_id, service_id, action_type, params, nonce, now, sig)
    assert replay_valid is False, "Nonce replay must be rejected!"


def test_timestamp_clock_drift_rejection():
    secret = "test_shared_agent_secret_key_32c"
    action_id = "act-old-999"
    service_id = "svc-67890"
    action_type = "restart_service"
    params = {}
    nonce = uuid.uuid4().hex

    # Timestamp 10 minutes in the past
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    sig = sign_payload(secret, action_id, service_id, action_type, params, nonce, stale_time.isoformat())

    # Verification must reject due to clock drift
    valid = verify_payload_signature(secret, action_id, service_id, action_type, params, nonce, stale_time, sig)
    assert valid is False


@pytest.mark.asyncio
async def test_simulated_agent_execution_receipt():
    secret = "sim_test_key_minimum_32_characters"
    client = SimulatedAgentClient(secret_key=secret)

    now = datetime.now(timezone.utc)
    nonce = uuid.uuid4().hex
    action_id = str(uuid.uuid4())
    service_id = str(uuid.uuid4())

    sig = sign_payload(
        secret, action_id, service_id, "restart_service", {}, nonce, now.isoformat()
    )

    req = ActionRequest(
        action_id=action_id,
        service_id=service_id,
        service_name="payment-service",
        action_type="restart_service",
        parameters={},
        nonce=nonce,
        timestamp=now,
        signature=sig,
    )

    res: ActionResult = await client.dispatch_action(req)
    assert res.status == ActionExecutionStatus.SUCCESS
    assert res.exit_code == 0
    assert len(res.evidence_receipt_hash) == 64
    assert "payment-service" in res.stdout_summary
    assert res.duration_ms >= 0


@pytest.mark.asyncio
async def test_simulated_agent_unapproved_action_rejection():
    secret = "sim_test_key_minimum_32_characters"
    client = SimulatedAgentClient(secret_key=secret)

    now = datetime.now(timezone.utc)
    nonce = uuid.uuid4().hex
    action_id = str(uuid.uuid4())

    # Pass unapproved action without signing check
    req = ActionRequest(
        action_id=action_id,
        service_id=str(uuid.uuid4()),
        service_name="payment-service",
        action_type="arbitrary_exec",
        parameters={"cmd": "whoami"},
        nonce=nonce,
        timestamp=now,
        signature="",
    )

    res = await client.dispatch_action(req)
    assert res.status == ActionExecutionStatus.REJECTED
    assert "Allowlist rejection" in res.stderr_summary
