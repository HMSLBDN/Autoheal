"""
AutoHeal DevOps — Recovery Engine & Health Verification Test Suite
Verifies action allowlist enforcement, controlled simulated execution,
post-recovery health verification, and RBAC authorization.
"""

from datetime import datetime, timezone
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models import Incident, Organization, RecoveryAction, RecoveryResult, Service, User
from app.services.recovery.executor import RecoveryExecutor
from app.services.recovery.registry import is_action_allowed
from app.services.recovery.verifier import PostRecoveryVerifier


@pytest.fixture
def recovery_client(db_session: AsyncSession) -> TestClient:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_recovery_action_allowlist():
    """Only approved least-privilege actions are allowed; arbitrary commands are rejected."""
    assert is_action_allowed("restart_service") is True
    assert is_action_allowed("clear_cache") is True
    assert is_action_allowed("scale_service") is True
    assert is_action_allowed("restore_health") is True
    assert is_action_allowed("rollback_release") is True

    # Dangerous commands must be rejected
    assert is_action_allowed("rm -rf /") is False
    assert is_action_allowed("systemctl stop firewall") is False
    assert is_action_allowed("docker run -v /:/root") is False
    assert is_action_allowed("eval") is False


@pytest.mark.asyncio
async def test_recovery_execution_and_health_verification_success(db_session: AsyncSession):
    """Execution of approved action normalizes service health, updates incident to resolved."""
    org = Organization(id=uuid.uuid4(), slug="rec-exec-org", name="Rec Exec Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    svc = Service(
        id="svc-checkout-rec",
        organization_id=org.id,
        name="checkout-api",
        environment="production",
        status="degraded",
        availability=97.5,
        error_rate=2.8,
        latency_ms=450,
        last_checked=datetime.now(timezone.utc),
    )
    inc = Incident(
        id="INC-REC-101",
        organization_id=org.id,
        service_id=svc.id,
        service_name=svc.name,
        title="High error rate on checkout",
        severity="high",
        status="open",
        detected_at=datetime.now(timezone.utc),
        recovery_status="Approved / Awaiting execution",
        error_rate=2.8,
        threshold=1.0,
    )
    rec = RecoveryAction(
        id="REC-SIM-101",
        incident_id=inc.id,
        service_id=svc.id,
        service_name=svc.name,
        action="restart_service",
        status="approved",
        approval_required=True,
        requested_by="Operator",
        requested_at=datetime.now(timezone.utc),
        verification="pending",
    )
    db_session.add_all([svc, inc, rec])
    await db_session.commit()

    executor = RecoveryExecutor()
    executed = await executor.execute_recovery(db_session, rec.id, simulated_outcome_healthy=True)

    assert executed.status == "completed"
    assert executed.verification == "passed"
    assert executed.result is not None
    assert executed.result.verified is True

    # Check incident transitioned to resolved
    await db_session.refresh(inc)
    assert inc.status == "resolved"
    assert inc.resolved_at is not None

    # Check service metrics normalized
    await db_session.refresh(svc)
    assert svc.status == "healthy"
    assert svc.error_rate < 0.1


@pytest.mark.asyncio
async def test_recovery_verification_failure_triggers_escalation(db_session: AsyncSession):
    """When post-recovery verification fails, incident is marked for escalation instead of resolved."""
    org = Organization(id=uuid.uuid4(), slug="rec-fail-org", name="Rec Fail Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    svc = Service(
        id="svc-fail-rec",
        organization_id=org.id,
        name="customer-web",
        environment="staging",
        status="critical",
        availability=85.0,
        error_rate=15.0,
        latency_ms=800,
        last_checked=datetime.now(timezone.utc),
    )
    inc = Incident(
        id="INC-FAIL-101",
        organization_id=org.id,
        service_id=svc.id,
        service_name=svc.name,
        title="Critical service outage",
        severity="critical",
        status="open",
        detected_at=datetime.now(timezone.utc),
        recovery_status="Approved / Awaiting execution",
        error_rate=15.0,
        threshold=1.0,
    )
    rec = RecoveryAction(
        id="REC-FAIL-101",
        incident_id=inc.id,
        service_id=svc.id,
        service_name=svc.name,
        action="restart_service",
        status="approved",
        approval_required=True,
        requested_by="Operator",
        requested_at=datetime.now(timezone.utc),
        verification="pending",
    )
    db_session.add_all([svc, inc, rec])
    await db_session.commit()

    executor = RecoveryExecutor()
    executed = await executor.execute_recovery(db_session, rec.id, simulated_outcome_healthy=False)

    assert executed.status == "completed"
    assert executed.verification == "failed"
    assert executed.result.verified is False

    await db_session.refresh(inc)
    assert inc.status == "investigating"
    assert "failed" in inc.recovery_status.lower()


@pytest.mark.asyncio
async def test_execute_recovery_endpoint_rbac(recovery_client: TestClient, db_session: AsyncSession):
    """POST /recoveries/{id}/execute requires Operator or Admin role."""
    org = Organization(id=uuid.uuid4(), slug="rbac-exec-org", name="RBAC Exec Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    viewer = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="viewer_exec@example.com",
        full_name="Viewer",
        hashed_password=get_password_hash("Password123!"),
        role="viewer",
        is_active=True,
    )
    operator = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="operator_exec@example.com",
        full_name="Operator",
        hashed_password=get_password_hash("Password123!"),
        role="operator",
        is_active=True,
    )
    db_session.add_all([viewer, operator])
    await db_session.flush()

    svc = Service(
        id="svc-rbac-test",
        organization_id=org.id,
        name="checkout-api",
        environment="production",
        status="healthy",
        availability=99.9,
        error_rate=0.0,
        latency_ms=100,
        last_checked=datetime.now(timezone.utc),
    )
    inc = Incident(
        id="INC-RBAC-EXEC",
        organization_id=org.id,
        service_id=svc.id,
        service_name=svc.name,
        title="RBAC Exec Test",
        severity="medium",
        status="open",
        detected_at=datetime.now(timezone.utc),
        recovery_status="Approved",
        error_rate=0.0,
        threshold=1.0,
    )
    rec = RecoveryAction(
        id="REC-RBAC-EXEC",
        incident_id=inc.id,
        service_id=svc.id,
        service_name=svc.name,
        action="clear_cache",
        status="approved",
        approval_required=True,
        requested_by="Operator",
        requested_at=datetime.now(timezone.utc),
        verification="pending",
    )
    db_session.add_all([svc, inc, rec])
    await db_session.commit()

    viewer_token = create_access_token(str(viewer.id), viewer.email, viewer.role, str(org.id))
    operator_token = create_access_token(str(operator.id), operator.email, operator.role, str(org.id))

    # Viewer gets 403 Forbidden
    res_viewer = recovery_client.post(
        f"/api/v1/recoveries/{rec.id}/execute",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert res_viewer.status_code == 403

    # Operator gets 200 OK and executes action
    res_operator = recovery_client.post(
        f"/api/v1/recoveries/{rec.id}/execute",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert res_operator.status_code == 200
    data = res_operator.json()
    assert data["status"] == "completed"
    assert data["verification"] == "passed"
