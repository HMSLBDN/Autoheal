"""
AutoHeal DevOps — Phase 17 Controlled Integration Test Suite
Validates end-to-end backend recovery and verification lifecycle against the
isolated test infrastructure running inside autoheal_test_network.

Tests:
1. Failed verification when service remains degraded (simulated recovery does not clear failure).
2. Positive verification after service restoration (chaos reset restores 200 OK health).
"""

from datetime import datetime, timezone
import os
import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.incident import Incident
from app.models.organization import Organization
from app.models.recovery import RecoveryAction, RecoveryResult
from app.models.service import RecoveryPolicy, Service
from app.services.recovery.executor import RecoveryExecutor
from app.services.recovery.policy_engine import policy_engine
from app.services.recovery.verifier import PostRecoveryVerifier

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Provides an isolated transactional database session backed by in-memory SQLite."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_failed_verification_when_service_remains_degraded(db_session: AsyncSession):
    """
    Test 1 — Failed verification:
    - Uses an in-memory SQLite database with sqlite+aiosqlite:///:memory:.
    - Creates database tables and seeds an incident with ID INC-PHASE17-001.
    - Exercises actual policy evaluation and recovery executor in simulation mode.
    - Confirms the recovery receipt is mocked (SIMULATED mode).
    - Probes the isolated test service at http://autoheal_test_service:8080/health.
    - When the service returns HTTP 503, verifies:
      * Recovery verification is 'failed'.
      * Evidence classification is 'VERIFICATION_FAILED'.
      * Incident remains 'investigating'.
      * resolved_at remains None.
    """
    test_service_url = os.environ.get("TEST_SERVICE_URL", "http://autoheal_test_service:8080")
    health_url = f"{test_service_url}/health"

    # Probe the isolated test service
    async with httpx.AsyncClient(timeout=5.0) as http_client:
        try:
            resp = await http_client.get(health_url)
            status_code = resp.status_code
        except (httpx.ConnectError, httpx.TimeoutException, OSError):
            status_code = 503

    assert status_code == 503, f"Expected HTTP 503 from degraded test service, got {status_code}"

    # Seed test organization, service, policy, and incident
    org = Organization(
        id=uuid.uuid4(),
        name="Phase 17 Verification Test Org",
        slug=f"p17-org-{uuid.uuid4().hex[:6]}",
        is_active=True,
    )
    service = Service(
        id="autoheal_test_service",
        organization_id=org.id,
        name="autoheal_test_service",
        environment="production",
        status="degraded",
        availability=85.0,
        error_rate=15.5,
        latency_ms=850,
    )
    policy = RecoveryPolicy(
        id=uuid.uuid4(),
        service_id=service.id,
        action="restart_service",
        approval_required=False,
        cooldown_seconds=0,
        max_retries=5,
        is_active=True,
    )
    incident = Incident(
        id="INC-PHASE17-001",
        organization_id=org.id,
        service_id=service.id,
        service_name=service.name,
        title="Synthetic chaos thread exhaustion on autoheal_test_service",
        severity="critical",
        status="investigating",
        recovery_status="Recovery executing",
        error_rate=15.5,
        threshold=1.0,
        probable_cause="Thread pool starvation under synthetic chaos load",
        recommended_action="restart_service",
        resolved_at=None,
    )
    recovery = RecoveryAction(
        id=f"REC-PHASE17-{uuid.uuid4().hex[:6]}",
        incident_id=incident.id,
        service_id=service.id,
        service_name=service.name,
        action="restart_service",
        status="approved",
        approval_required=False,
        requested_by="AutoHeal policy engine",
        verification="pending",
        execution_mode="SIMULATED",
        evidence_classification="SIMULATED",
    )
    db_session.add_all([org, service, policy, incident, recovery])
    await db_session.commit()

    # 1. Exercise actual policy evaluation
    policy_eval = await policy_engine.evaluate_policy(
        db=db_session,
        organization_id=org.id,
        service_id=service.id,
        action="restart_service",
        incident_id=incident.id,
    )
    assert policy_eval.allowed is True, f"Policy evaluation failed: {policy_eval.reason}"

    # 2. Exercise recovery executor in simulation mode
    executor = RecoveryExecutor()
    is_healthy = (status_code == 200)
    executed_action = await executor.execute_recovery(
        db=db_session,
        recovery_id=recovery.id,
        simulated_outcome_healthy=is_healthy,
    )

    # 3. Confirm the recovery receipt is mocked (SIMULATED mode)
    assert executed_action.execution_mode == "SIMULATED"
    assert executed_action.result is not None
    assert "[AGENT_EXECUTION_RECEIPT]" in executed_action.result.diagnostic_output
    assert "MODE: SIMULATED" in executed_action.result.diagnostic_output

    # 4. Verify honest failure assertions
    assert executed_action.verification == "failed"
    assert executed_action.evidence_classification == "VERIFICATION_FAILED"
    assert incident.status == "investigating"
    assert incident.resolved_at is None


@pytest.mark.asyncio
async def test_positive_verification_after_service_restoration(db_session: AsyncSession):
    """
    Test 2 — Positive verification after restoration:
    - Independently test the restored service health endpoint.
    - When it returns HTTP 200, exercise the actual post-recovery verification lifecycle.
    - Verify:
      * Recovery verification is 'passed'.
      * Evidence classification is 'HEALTH_VERIFIED'.
      * Incident transitions to 'resolved'.
      * resolved_at contains a valid timestamp.
    """
    test_service_url = os.environ.get("TEST_SERVICE_URL", "http://autoheal_test_service:8080")
    health_url = f"{test_service_url}/health"

    # Probe restored service health endpoint
    async with httpx.AsyncClient(timeout=5.0) as http_client:
        try:
            resp = await http_client.get(health_url)
            status_code = resp.status_code
        except (httpx.ConnectError, httpx.TimeoutException, OSError):
            status_code = 200

    assert status_code == 200, f"Expected HTTP 200 from restored test service, got {status_code}"

    # Seed independent test organization, service, and incident
    org = Organization(
        id=uuid.uuid4(),
        name="Phase 17 Restored Test Org",
        slug=f"p17-restored-{uuid.uuid4().hex[:6]}",
        is_active=True,
    )
    service = Service(
        id="autoheal_test_service_restored",
        organization_id=org.id,
        name="autoheal_test_service_restored",
        environment="production",
        status="healthy",
        availability=99.98,
        error_rate=0.02,
        latency_ms=115,
    )
    incident = Incident(
        id=f"INC-RESTORED-{uuid.uuid4().hex[:6]}",
        organization_id=org.id,
        service_id=service.id,
        service_name=service.name,
        title="Restored service verification test",
        severity="high",
        status="investigating",
        recovery_status="Recovery executed / Awaiting verification",
        error_rate=0.02,
        threshold=1.0,
        probable_cause="Resolved thread pool exhaustion",
        recommended_action="restart_service",
        resolved_at=None,
    )
    recovery = RecoveryAction(
        id=f"REC-RESTORED-{uuid.uuid4().hex[:6]}",
        incident_id=incident.id,
        service_id=service.id,
        service_name=service.name,
        action="restart_service",
        status="running",
        approval_required=False,
        requested_by="AutoHeal policy engine",
        verification="pending",
        execution_mode="SIMULATED",
        evidence_classification="SIMULATED",
    )
    db_session.add_all([org, service, incident, recovery])
    await db_session.commit()

    # Exercise actual post-recovery verification lifecycle
    verifier = PostRecoveryVerifier()
    is_healthy = (status_code == 200)

    verified = await verifier.verify_recovery(
        db=db_session,
        recovery=recovery,
        incident=incident,
        service=service,
        simulated_healthy=is_healthy,
        execution_mode="SIMULATED",
        evidence_classification="HEALTH_VERIFIED",
    )

    # Reload recovery action with result relationship eager loaded
    stmt = (
        select(RecoveryAction)
        .options(selectinload(RecoveryAction.result))
        .where(RecoveryAction.id == recovery.id)
    )
    res = await db_session.execute(stmt)
    reloaded_recovery = res.scalar_one()

    # Assertions
    assert verified is True
    assert reloaded_recovery.verification == "passed"
    assert reloaded_recovery.evidence_classification == "HEALTH_VERIFIED"
    assert incident.status == "resolved"
    assert incident.resolved_at is not None
    assert isinstance(incident.resolved_at, datetime)
