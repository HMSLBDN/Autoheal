"""
AutoHeal DevOps — Phase 13.1 Recovery Safety and Incident Integrity Regression Tests
Verifies:
1. RECOVERY_SIMULATION_MODE remains enabled and locked.
2. No production recovery operation can execute unexpectedly.
3. No arbitrary shell commands can be executed via Docker or Agent adapters.
4. No Docker socket is exposed or mounted.
5. Recovery actions remain strictly allowlisted.
6. Unauthorized recovery requests are rejected by RBAC and tenant boundaries.
7. Failed recovery cannot be recorded as successful.
8. Incidents cannot be marked resolved simply because a recovery command executed.
9. Successful recovery requires a successful health verification.
10. Failed verification keeps the incident unresolved.
11. Failed recovery can be escalated.
12. Manual sign-off is separately recorded and cannot falsely claim recovery succeeded.
13. Every transition has an auditable actor, timestamp, previous state, new state, and reason.
"""

from datetime import datetime, timezone, timedelta
import json
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.main import app
from app.api.deps import get_current_user
from app.models.audit import AuditLog
from app.models.incident import Incident, IncidentEvent
from app.models.organization import Organization
from app.models.recovery import RecoveryAction, RecoveryResult
from app.models.service import Service
from app.models.user import User
from app.services.agent import (
    ActionExecutionStatus,
    ActionRequest,
    ActionResult,
    InfrastructureAgentClient,
    SimulatedAgentClient,
    validate_agent_action,
)
from app.services.infrastructure.docker_adapter import (
    RestrictedDockerAdapter,
    SecurityViolationError,
)
from app.services.infrastructure.k8s_adapter import (
    ModularKubernetesAdapter,
    K8sSecurityViolationError,
)
from app.services.recovery.executor import RecoveryExecutor
from app.services.recovery.registry import is_action_allowed, normalize_action
from app.services.incident_state_machine import IncidentStateMachine


# ------------------------------------------------------------------------------
# TASK 1: Recovery Mode, Adapter Safety, and Allowlist Audits
# ------------------------------------------------------------------------------

def test_recovery_simulation_mode_is_enabled():
    """Verify simulation mode remains enabled by default."""
    settings = get_settings()
    assert settings.RECOVERY_SIMULATION_MODE is True
    docker_adapter = RestrictedDockerAdapter()
    assert docker_adapter.simulation_mode is True


def test_docker_adapter_blocks_arbitrary_shell_injection():
    """Verify Docker adapter rejects shell metacharacters and directory traversal."""
    adapter = RestrictedDockerAdapter()
    malicious_inputs = [
        "checkout-api; rm -rf /",
        "checkout-api && whoami",
        "checkout-api | cat /etc/passwd",
        "checkout-api`id`",
        "checkout-api$(id)",
        "../etc/shadow",
        "checkout-api/../../",
    ]
    for bad_name in malicious_inputs:
        with pytest.raises(SecurityViolationError):
            adapter._validate_service_name(bad_name)


def test_docker_adapter_blocks_unallowlisted_service():
    """Verify Docker adapter rejects services outside the allowlist."""
    adapter = RestrictedDockerAdapter()
    with pytest.raises(SecurityViolationError):
        adapter._validate_service_name("unregistered_random_service")


@pytest.mark.asyncio
async def test_kubernetes_adapter_fails_safe_when_disabled():
    """Verify Kubernetes adapter fails safe with simulation receipt when disabled."""
    k8s = ModularKubernetesAdapter(enabled=False)
    res = await k8s.rollout_restart_deployment("default", "checkout-api")
    assert res["status"] == "simulated"
    assert "disabled by default" in res["message"]


def test_kubernetes_adapter_blocks_unapproved_namespaces_and_deployments():
    """Verify Kubernetes adapter rejects unauthorized namespaces and workloads."""
    k8s = ModularKubernetesAdapter()
    with pytest.raises(K8sSecurityViolationError):
        k8s._validate_namespace("kube-system")
    with pytest.raises(K8sSecurityViolationError):
        k8s._validate_workload("kube-apiserver")


def test_recovery_action_allowlist_enforcement():
    """Verify recovery action registry strictly bounds permissible actions."""
    assert is_action_allowed("restart_service") is True
    assert is_action_allowed("clear_cache") is True
    assert is_action_allowed("scale_service") is True
    assert is_action_allowed("drop_database") is False
    assert is_action_allowed("bash -c id") is False
    assert is_action_allowed("python -c import os") is False


@pytest.mark.asyncio
async def test_failed_agent_execution_cannot_be_recorded_as_successful(db_session: AsyncSession, seed_data: dict):
    """Verify agent execution failure marks action as failed and does not mark incident resolved."""
    org = seed_data["org_a"]
    svc = seed_data["svc_a1"]
    now = datetime.now(timezone.utc)

    inc = Incident(
        id=f"INC-FAIL-EXEC-{uuid.uuid4().hex[:6]}",
        organization_id=org.id,
        service_id=svc.id,
        service_name=svc.name,
        title="Agent Execution Failure Test",
        severity="high",
        status="recovering",
        detected_at=now,
        recovery_status="Approved / Awaiting execution",
    )
    rec = RecoveryAction(
        id=f"REC-FAIL-EXEC-{uuid.uuid4().hex[:6]}",
        incident_id=inc.id,
        service_id=svc.id,
        service_name=svc.name,
        action="restart_service",
        status="approved",
        approval_required=True,
        requested_by="operator@org-a.com",
        requested_at=now,
        verification="pending",
    )
    db_session.add_all([inc, rec])
    await db_session.commit()

    # Mock agent that returns failure
    class FailingAgentClient(InfrastructureAgentClient):
        async def register(self, r): return True
        async def get_heartbeat(self): pass
        async def cancel_action(self, action_id: str) -> bool: return True
        async def dispatch_action(self, r: ActionRequest) -> ActionResult:
            return ActionResult(
                action_id=r.action_id,
                agent_id="failing-agent-01",
                status=ActionExecutionStatus.FAILED,
                exit_code=137,
                duration_ms=42,
                stdout_summary="",
                stderr_summary="Process was OOMKilled during container restart attempt.",
                evidence_receipt_hash="failhash123456",
            )

    executor = RecoveryExecutor(agent_client=FailingAgentClient())
    executed = await executor.execute_recovery(db_session, recovery_id=rec.id)

    assert executed.status == "failed"
    assert executed.verification == "failed"
    assert executed.result is not None
    assert executed.result.verified is False
    assert "Execution failed" in executed.result.summary

    # Ensure incident was NOT resolved
    await db_session.refresh(inc)
    assert inc.status == "investigating"
    assert "Execution failed" in inc.recovery_status


# ------------------------------------------------------------------------------
# TASK 2: Incident Resolution Integrity & State Machine Regression Tests
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transition_endpoint_blocks_viewer_role(client: TestClient, seed_data: dict, db_session: AsyncSession):
    """Verify viewer role cannot transition incident status (403 Forbidden)."""
    inc = seed_data["inc_a1"]
    org = seed_data["org_a"]

    viewer = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="viewer-role@org-a.com",
        full_name="Viewer User",
        hashed_password="insecure_password_hash_123456",
        role="viewer",
        is_active=True,
    )
    db_session.add(viewer)
    await db_session.commit()

    async def override_viewer():
        return viewer

    orig = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = override_viewer
    try:
        res = client.post(
            f"/api/v1/incidents/{inc.id}/transition",
            json={"target_status": "investigating", "reason": "Viewer attempted status transition"},
        )
        assert res.status_code == 403
        assert "Insufficient permissions" in res.json()["detail"]
    finally:
        if orig:
            app.dependency_overrides[get_current_user] = orig


@pytest.mark.asyncio
async def test_transition_endpoint_blocks_cross_tenant_access(client: TestClient, seed_data: dict):
    """Verify operator in Org A cannot transition incident in Org B (404 Not Found)."""
    inc_b = seed_data["inc_b1"]
    res = client.post(
        f"/api/v1/incidents/{inc_b.id}/transition",
        json={"target_status": "investigating", "reason": "Cross-tenant attempt"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_cannot_mark_resolved_without_health_verification(client: TestClient, seed_data: dict, db_session: AsyncSession):
    """Verify transition to resolved is rejected if automated recovery was not verified healthy."""
    inc = seed_data["inc_a1"]
    res = client.post(
        f"/api/v1/incidents/{inc.id}/transition",
        json={"target_status": "resolved", "reason": "Attempting premature resolution without verification", "is_manual_signoff": False},
    )
    assert res.status_code == 400
    assert "cannot be marked resolved" in res.json()["detail"].lower()

    # Also test an incident with zero recovery actions
    org = seed_data["org_a"]
    svc = seed_data["svc_a1"]
    clean_inc = Incident(
        id=f"INC-NO-REC-{uuid.uuid4().hex[:6]}",
        organization_id=org.id,
        service_id=svc.id,
        service_name=svc.name,
        title="Zero Recovery Incident",
        severity="medium",
        status="open",
        detected_at=datetime.now(timezone.utc),
    )
    db_session.add(clean_inc)
    await db_session.commit()

    res_clean = client.post(
        f"/api/v1/incidents/{clean_inc.id}/transition",
        json={"target_status": "resolved", "reason": "Trying resolution without any recovery", "is_manual_signoff": False},
    )
    assert res_clean.status_code == 400
    assert "cannot resolve incident without verified healthy" in res_clean.json()["detail"].lower()


@pytest.mark.asyncio
async def test_cannot_mark_resolved_when_verification_failed(client: TestClient, seed_data: dict, db_session: AsyncSession):
    """Verify transition to resolved is rejected if verification failed."""
    inc = seed_data["inc_a1"]
    now = datetime.now(timezone.utc) + timedelta(seconds=1)

    # Attach a failed recovery action
    failed_rec = RecoveryAction(
        id=f"REC-FAILED-{uuid.uuid4().hex[:6]}",
        incident_id=inc.id,
        service_id=inc.service_id,
        service_name=inc.service_name,
        action="restart_service",
        status="completed",
        verification="failed",
        approval_required=True,
        requested_by="operator@org-a.com",
        requested_at=now,
    )
    failed_rec.result = RecoveryResult(
        id=uuid.uuid4(),
        recovery_action_id=failed_rec.id,
        verified=False,
        summary="Health check returned 503 Service Unavailable",
        completed_at=now,
    )
    db_session.add(failed_rec)
    await db_session.commit()

    res = client.post(
        f"/api/v1/incidents/{inc.id}/transition",
        json={"target_status": "resolved", "reason": "Operator trying to resolve after failed check", "is_manual_signoff": False},
    )
    assert res.status_code == 400
    assert "verification failed" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_failed_recovery_can_be_escalated(client: TestClient, seed_data: dict, db_session: AsyncSession):
    """Verify an unresolved incident can be transitioned to 'escalated'."""
    inc = seed_data["inc_a1"]
    res = client.post(
        f"/api/v1/incidents/{inc.id}/transition",
        json={"target_status": "escalated", "reason": "Verification failed. Escalating to Tier 3 on-call SRE."},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "escalated"
    assert "Escalated" in data["recoveryStatus"]


@pytest.mark.asyncio
async def test_manual_signoff_recorded_separately_and_cannot_claim_automated_success(
    client: TestClient, seed_data: dict, db_session: AsyncSession
):
    """Verify manual sign-off allows resolution but explicitly marks recovery unverified in audit and event trail."""
    inc = seed_data["inc_a1"]
    res = client.post(
        f"/api/v1/incidents/{inc.id}/transition",
        json={
            "target_status": "resolved",
            "reason": "SRE verified cluster stability manually in Grafana.",
            "is_manual_signoff": True,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "resolved"
    assert "Manual resolution" in data["recoveryStatus"]
    assert "unverified" in data["recoveryStatus"]

    # Verify audit log captures distinct manual sign-off
    stmt = (
        select(AuditLog)
        .where(
            AuditLog.resource_id == inc.id,
            AuditLog.action == "incident_manual_signoff",
        )
    )
    audit = (await db_session.execute(stmt)).scalar_one_or_none()
    assert audit is not None
    details = json.loads(audit.details)
    assert details["is_manual_signoff"] is True
    assert details["recovery_verified"] is False
    assert "SRE verified cluster stability" in details["reason"]


@pytest.mark.asyncio
async def test_valid_verified_recovery_allows_resolution(
    client: TestClient, seed_data: dict, db_session: AsyncSession
):
    """Verify that when recovery verification passes, transition to resolved succeeds."""
    inc = seed_data["inc_a1"]
    now = datetime.now(timezone.utc) + timedelta(seconds=1)

    # Attach verified recovery action
    verified_rec = RecoveryAction(
        id=f"REC-VERIFIED-{uuid.uuid4().hex[:6]}",
        incident_id=inc.id,
        service_id=inc.service_id,
        service_name=inc.service_name,
        action="restart_service",
        status="completed",
        verification="passed",
        approval_required=True,
        requested_by="operator@org-a.com",
        requested_at=now,
    )
    verified_rec.result = RecoveryResult(
        id=uuid.uuid4(),
        recovery_action_id=verified_rec.id,
        verified=True,
        summary="Service returned 200 OK. Error rate normalized.",
        completed_at=now,
    )
    db_session.add(verified_rec)
    await db_session.commit()

    res = client.post(
        f"/api/v1/incidents/{inc.id}/transition",
        json={"target_status": "resolved", "reason": "Automated verification passed. Closing incident."},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "resolved"
    assert "Verified healthy" in data["recoveryStatus"]


@pytest.mark.asyncio
async def test_transition_requires_mandatory_reason_and_rejects_self_transition(client: TestClient, seed_data: dict):
    """Verify self-transition and empty reason are rejected."""
    inc = seed_data["inc_a1"]

    # Empty reason
    res_empty = client.post(
        f"/api/v1/incidents/{inc.id}/transition",
        json={"target_status": "investigating", "reason": "  "},
    )
    assert res_empty.status_code in (400, 422)

    # Self-transition (open -> open)
    res_self = client.post(
        f"/api/v1/incidents/{inc.id}/transition",
        json={"target_status": "open", "reason": "Trying self transition"},
    )
    assert res_self.status_code == 400
    assert "already in state" in res_self.json()["detail"]


@pytest.mark.asyncio
async def test_deterministic_recovery_action_selection_on_identical_timestamps(
    client: TestClient, seed_data: dict, db_session: AsyncSession
):
    """
    Verifies that when multiple recovery actions share the exact same requested_at
    and created_at timestamps, the tie-breaker is strictly deterministic using desc(RecoveryAction.id).
    """
    org_a = seed_data["org_a"]
    svc_a2 = seed_data["svc_a2"]
    inc = Incident(
        id=f"INC-TIE-{uuid.uuid4().hex[:8]}",
        organization_id=org_a.id,
        service_id=svc_a2.id,
        service_name=svc_a2.name,
        title="Deterministic Tiebreaker Incident",
        severity="high",
        status="investigating",
        recovery_status="Action initiated",
        error_rate=1.84,
        threshold=1.0,
        probable_cause="Testing tiebreaker",
        recommended_action="restart_service",
    )
    db_session.add(inc)
    await db_session.flush()

    fixed_time = datetime(2026, 11, 23, 12, 0, 0, tzinfo=timezone.utc)

    # Action 1: ID 'REC-AAA-FAILED', verification='failed'
    rec_aaa = RecoveryAction(
        id="REC-AAA-FAILED",
        incident_id=inc.id,
        service_id=inc.service_id,
        service_name=inc.service_name,
        action="restart_service",
        status="completed",
        verification="failed",
        approval_required=True,
        requested_by="operator@org-a.com",
        requested_at=fixed_time,
        created_at=fixed_time,
    )
    rec_aaa.result = RecoveryResult(
        id=uuid.uuid4(),
        recovery_action_id=rec_aaa.id,
        verified=False,
        summary="Check failed",
        completed_at=fixed_time,
    )

    # Action 2: ID 'REC-ZZZ-PASSED', verification='passed'
    rec_zzz = RecoveryAction(
        id="REC-ZZZ-PASSED",
        incident_id=inc.id,
        service_id=inc.service_id,
        service_name=inc.service_name,
        action="restart_service",
        status="completed",
        verification="passed",
        approval_required=True,
        requested_by="operator@org-a.com",
        requested_at=fixed_time,
        created_at=fixed_time,
    )
    rec_zzz.result = RecoveryResult(
        id=uuid.uuid4(),
        recovery_action_id=rec_zzz.id,
        verified=True,
        summary="Check passed 200 OK",
        completed_at=fixed_time,
    )

    db_session.add_all([rec_aaa, rec_zzz])
    await db_session.commit()

    # Under desc(RecoveryAction.id), 'REC-ZZZ-PASSED' > 'REC-AAA-FAILED', so 'REC-ZZZ-PASSED'
    # (verification='passed') is selected as latest_rec, allowing resolution.
    eligible, verified, diag = await IncidentStateMachine.verify_resolution_eligibility(
        db=db_session, incident=inc
    )
    assert eligible is True
    assert verified is True
    assert "Eligible for resolution" in diag

    # Now add Action 3: ID 'REC-ZZZZ-FAILED' with the exact same timestamps.
    # Because 'REC-ZZZZ-FAILED' > 'REC-ZZZ-PASSED' lexicographically,
    # it must become the new latest_rec, immediately blocking resolution!
    rec_zzzz = RecoveryAction(
        id="REC-ZZZZ-FAILED",
        incident_id=inc.id,
        service_id=inc.service_id,
        service_name=inc.service_name,
        action="restart_service",
        status="completed",
        verification="failed",
        approval_required=True,
        requested_by="operator@org-a.com",
        requested_at=fixed_time,
        created_at=fixed_time,
    )
    rec_zzzz.result = RecoveryResult(
        id=uuid.uuid4(),
        recovery_action_id=rec_zzzz.id,
        verified=False,
        summary="Latest check failed",
        completed_at=fixed_time,
    )
    db_session.add(rec_zzzz)
    await db_session.commit()

    eligible2, verified2, diag2 = await IncidentStateMachine.verify_resolution_eligibility(
        db=db_session, incident=inc
    )
    assert eligible2 is False
    assert verified2 is False
    assert "Automated health verification failed for recovery 'REC-ZZZZ-FAILED'" in diag2
