"""
AutoHeal DevOps — Phase 17 Controlled Integration & Hermetic Lifecycle Test Suite
Validates end-to-end backend recovery and verification lifecycle:
1. Live HTTP Integration Tests (require isolated Docker test container autoheal_test_service:8080).
2. Hermetic Backend Lifecycle Tests (execute completely in-memory without network coupling).
"""

from datetime import datetime, timezone
import logging
import os
import socket
import sys
import urllib.parse
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

logger = logging.getLogger(__name__)

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


def validate_test_service_url(raw_url: str) -> str:
    """
    Validates that the test service URL points strictly to the isolated Docker test container.
    Strictly requires the normalized URL to match exactly: http://autoheal_test_service:8080.
    Rejects:
    - Trailing slashes
    - Any URL path
    - Query parameters, including empty query delimiters ('?')
    - Fragments, including empty fragment delimiters ('#')
    - User credentials or delimiters ('@')
    - Unexpected hostname, scheme, or port
    """
    if not raw_url or not isinstance(raw_url, str):
        raise ValueError("Security violation: TEST_SERVICE_URL must be a non-empty string.")

    if raw_url != raw_url.strip():
        raise ValueError(
            "Security violation: Test service URL must not contain surrounding whitespace."
        )

    url = raw_url

    # Reject query parameter delimiters, including empty ones
    if "?" in url:
        raise ValueError("Security violation: Test service URL must not contain query parameters or delimiters ('?').")

    # Reject fragment delimiters, including empty ones
    if "#" in url:
        raise ValueError("Security violation: Test service URL must not contain fragments or fragment delimiters ('#').")

    # Reject credentials or credential delimiters
    if "@" in url:
        raise ValueError("Security violation: Test service URL must not contain user credentials or delimiters ('@').")

    # Reject trailing slashes
    if url.endswith("/"):
        raise ValueError("Security violation: Test service URL must not contain a trailing slash.")

    parsed = urllib.parse.urlparse(url)

    if parsed.scheme != "http":
        raise ValueError(f"Security violation: Test service scheme must be strictly 'http', got '{parsed.scheme}'.")

    if parsed.username or parsed.password:
        raise ValueError("Security violation: Test service URL must not contain user credentials.")

    if parsed.hostname != "autoheal_test_service":
        raise ValueError(
            f"Security violation: Test service hostname must be strictly 'autoheal_test_service' for Docker-based execution, "
            f"got '{parsed.hostname}'. Localhost, 127.0.0.1, and external hosts are strictly forbidden."
        )

    if parsed.port != 8080:
        raise ValueError(f"Security violation: Test service port must be explicitly 8080, got '{parsed.port}'.")

    if parsed.path:
        raise ValueError(f"Security violation: Test service URL must not contain any path, got '{parsed.path}'.")

    if parsed.query:
        raise ValueError(f"Security violation: Test service URL must not contain query parameters, got '{parsed.query}'.")

    if parsed.fragment:
        raise ValueError(f"Security violation: Test service URL must not contain a URL fragment, got '{parsed.fragment}'.")

    if url != "http://autoheal_test_service:8080":
        raise ValueError(
            f"Security violation: Normalized test service URL must match exactly 'http://autoheal_test_service:8080', got '{url}'."
        )

    return "http://autoheal_test_service:8080"


def is_test_service_available(base_url: str) -> bool:
    """Preflight check probing whether the isolated test service is active and responsive."""
    parsed = urllib.parse.urlparse(base_url)
    host = parsed.hostname
    port = parsed.port or 80
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except (socket.error, OSError):
        return False


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Provides an isolated transactional database session backed by in-memory SQLite."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def require_live_test_service():
    """
    Preflight check enforcing that the isolated Docker test container
    'autoheal_test_service:8080' is running and reachable.
    If unavailable, explicitly skips the live integration test with a clear reason.
    """
    raw_url = os.environ.get("TEST_SERVICE_URL", "http://autoheal_test_service:8080")
    base_url = validate_test_service_url(raw_url)

    if not is_test_service_available(base_url):
        pytest.skip(
            f"Live integration service '{base_url}' is unavailable. "
            "Live HTTP integration tests require the isolated Docker test network (autoheal_test_network). "
            "Skipping live integration test."
        )
    return base_url


@pytest_asyncio.fixture(scope="function")
async def degraded_test_service(require_live_test_service: str):
    """
    Independent async fixture establishing a degraded test service state:
    1. Validates TEST_SERVICE_URL strictly requiring http://autoheal_test_service:8080.
    2. Calls POST /chaos/degrade on the live service.
    3. Verifies GET /health returns HTTP 503.
    4. Yields the service URL to the test.
    5. Restores the service via POST /chaos/recover during teardown.
    6. Verifies GET /health returns HTTP 200.
    """
    base_url = require_live_test_service

    async with httpx.AsyncClient(timeout=5.0) as client:
        # Setup: Degrade service
        degrade_resp = await client.post(f"{base_url}/chaos/degrade")
        if degrade_resp.status_code != 200:
            raise RuntimeError(
                f"Setup failure: POST /chaos/degrade returned HTTP {degrade_resp.status_code}"
            )
        health_resp = await client.get(f"{base_url}/health")
        if health_resp.status_code != 503:
            raise RuntimeError(
                f"Setup verification failed: Expected HTTP 503 from /health, got {health_resp.status_code}"
            )

    test_exc = None
    try:
        yield base_url
    except BaseException as exc:
        test_exc = exc
        raise
    finally:
        # Teardown: Unconditionally restore service to healthy state
        teardown_exc = None
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                recover_resp = await client.post(f"{base_url}/chaos/recover")
                if recover_resp.status_code != 200:
                    raise RuntimeError(
                        f"Teardown failure: POST /chaos/recover returned HTTP {recover_resp.status_code}"
                    )
                health_verify = await client.get(f"{base_url}/health")
                if health_verify.status_code != 200:
                    raise RuntimeError(
                        f"Teardown verification failed: Expected HTTP 200 from /health, got {health_verify.status_code}"
                    )
        except Exception as err:
            teardown_exc = err
            logger.error(
                "[TEST_SERVICE_TEARDOWN_FAILURE] Teardown cleanup failed for %s: %s",
                base_url,
                err,
            )
            print(
                f"\n[TEST_SERVICE_TEARDOWN_FAILURE] Critical cleanup error for {base_url}: {err}\n",
                file=sys.stderr,
            )

        if teardown_exc is not None:
            if test_exc is not None:
                raise RuntimeError(
                    f"Teardown cleanup failed after test failure: {teardown_exc}"
                ) from test_exc
            else:
                raise RuntimeError(f"Teardown cleanup failed: {teardown_exc}")


@pytest_asyncio.fixture(scope="function")
async def healthy_test_service(require_live_test_service: str):
    """
    Independent async fixture establishing a healthy test service state:
    1. Validates TEST_SERVICE_URL strictly requiring http://autoheal_test_service:8080.
    2. Ensures the service is healthy using POST /chaos/recover.
    3. Verifies GET /health returns HTTP 200.
    4. Yields the service URL.
    5. Ensures the service remains healthy during teardown (POST /chaos/recover + GET /health 200).
    """
    base_url = require_live_test_service

    async with httpx.AsyncClient(timeout=5.0) as client:
        # Setup: Reset to healthy state
        recover_resp = await client.post(f"{base_url}/chaos/recover")
        if recover_resp.status_code != 200:
            raise RuntimeError(
                f"Setup failure: POST /chaos/recover returned HTTP {recover_resp.status_code}"
            )
        health_resp = await client.get(f"{base_url}/health")
        if health_resp.status_code != 200:
            raise RuntimeError(
                f"Setup verification failed: Expected HTTP 200 from /health, got {health_resp.status_code}"
            )

    test_exc = None
    try:
        yield base_url
    except BaseException as exc:
        test_exc = exc
        raise
    finally:
        # Teardown: Ensure clean healthy state post-test
        teardown_exc = None
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                recover_resp = await client.post(f"{base_url}/chaos/recover")
                if recover_resp.status_code != 200:
                    raise RuntimeError(
                        f"Teardown failure: POST /chaos/recover returned HTTP {recover_resp.status_code}"
                    )
                health_verify = await client.get(f"{base_url}/health")
                if health_verify.status_code != 200:
                    raise RuntimeError(
                        f"Teardown verification failed: Expected HTTP 200 from /health, got {health_verify.status_code}"
                    )
        except Exception as err:
            teardown_exc = err
            logger.error(
                "[TEST_SERVICE_TEARDOWN_FAILURE] Teardown cleanup failed for %s: %s",
                base_url,
                err,
            )
            print(
                f"\n[TEST_SERVICE_TEARDOWN_FAILURE] Critical cleanup error for {base_url}: {err}\n",
                file=sys.stderr,
            )

        if teardown_exc is not None:
            if test_exc is not None:
                raise RuntimeError(
                    f"Teardown cleanup failed after test failure: {teardown_exc}"
                ) from test_exc
            else:
                raise RuntimeError(f"Teardown cleanup failed: {teardown_exc}")


# ==============================================================================
# 1. LIVE HTTP INTEGRATION TESTS (Require Docker Network Mesh)
# ==============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_failed_verification_when_service_remains_degraded(
    db_session: AsyncSession,
    degraded_test_service: str,
):
    """
    Live Integration Test 1 — Failed verification when service remains degraded:
    - Queries the isolated test service at http://autoheal_test_service:8080/health.
    - Validates real HTTP 503 response from live degraded service (NO fallback simulation).
    - Exercises actual policy evaluation and recovery executor in simulation mode.
    - Confirms the recovery receipt is mocked (SIMULATED mode).
    - Confirms honest failure assertions:
      * Recovery verification is 'failed'.
      * Evidence classification is 'VERIFICATION_FAILED'.
      * Incident remains 'investigating'.
      * resolved_at remains None.
    """
    test_service_url = degraded_test_service
    health_url = f"{test_service_url}/health"

    # Probe the live isolated test service (no exception fallback to 503)
    async with httpx.AsyncClient(timeout=5.0) as http_client:
        resp = await http_client.get(health_url)
        status_code = resp.status_code

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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_positive_verification_after_service_restoration(
    db_session: AsyncSession,
    healthy_test_service: str,
):
    """
    Live Integration Test 2 — Positive verification after restoration:
    - Queries the live restored service health endpoint.
    - Validates real HTTP 200 response from live restored service (NO fallback simulation).
    - Exercise actual post-recovery verification lifecycle.
    - Verifies:
      * Recovery verification is 'passed'.
      * Evidence classification is 'HEALTH_VERIFIED'.
      * Incident transitions to 'resolved'.
      * resolved_at contains a valid timestamp.
    """
    test_service_url = healthy_test_service
    health_url = f"{test_service_url}/health"

    # Probe restored service health endpoint (no exception fallback to 200)
    async with httpx.AsyncClient(timeout=5.0) as http_client:
        resp = await http_client.get(health_url)
        status_code = resp.status_code

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


# ==============================================================================
# 2. HERMETIC BACKEND LIFECYCLE TESTS (No Docker / Offline Verification)
# ==============================================================================

@pytest.mark.asyncio
async def test_hermetic_failed_verification_lifecycle(db_session: AsyncSession):
    """
    Hermetic Unit Test — Failed verification backend lifecycle:
    - Runs completely in-memory without external Docker containers or network dependencies.
    - Exercises actual policy evaluation and recovery executor with simulated degraded outcome (503).
    - Asserts that when post-recovery verification fails:
      * Recovery verification is 'failed'.
      * Evidence classification is 'VERIFICATION_FAILED'.
      * Incident remains 'investigating'.
      * resolved_at remains None.
    """
    org = Organization(
        id=uuid.uuid4(),
        name="Hermetic Verification Test Org",
        slug=f"herm-org-{uuid.uuid4().hex[:6]}",
        is_active=True,
    )
    service = Service(
        id="hermetic_test_service_degraded",
        organization_id=org.id,
        name="hermetic_test_service_degraded",
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
        id=f"INC-HERM-DEG-{uuid.uuid4().hex[:6]}",
        organization_id=org.id,
        service_id=service.id,
        service_name=service.name,
        title="Simulated degradation under chaos",
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
        id=f"REC-HERM-DEG-{uuid.uuid4().hex[:6]}",
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

    # 2. Exercise recovery executor in simulation mode with simulated degraded outcome
    executor = RecoveryExecutor()
    executed_action = await executor.execute_recovery(
        db=db_session,
        recovery_id=recovery.id,
        simulated_outcome_healthy=False,
    )

    # 3. Confirm execution mode and receipt
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
async def test_hermetic_positive_verification_lifecycle(db_session: AsyncSession):
    """
    Hermetic Unit Test — Positive verification backend lifecycle:
    - Runs completely in-memory without external Docker containers or network dependencies.
    - Exercises actual PostRecoveryVerifier lifecycle with simulated healthy outcome (200).
    - Asserts that when post-recovery verification passes:
      * Recovery verification is 'passed'.
      * Evidence classification is 'HEALTH_VERIFIED'.
      * Incident transitions to 'resolved'.
      * resolved_at contains a valid timestamp.
    """
    org = Organization(
        id=uuid.uuid4(),
        name="Hermetic Restored Test Org",
        slug=f"herm-restored-{uuid.uuid4().hex[:6]}",
        is_active=True,
    )
    service = Service(
        id="hermetic_test_service_restored",
        organization_id=org.id,
        name="hermetic_test_service_restored",
        environment="production",
        status="healthy",
        availability=99.98,
        error_rate=0.02,
        latency_ms=115,
    )
    incident = Incident(
        id=f"INC-HERM-REST-{uuid.uuid4().hex[:6]}",
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
        id=f"REC-HERM-REST-{uuid.uuid4().hex[:6]}",
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

    # Exercise actual post-recovery verification lifecycle with simulated healthy outcome
    verifier = PostRecoveryVerifier()
    verified = await verifier.verify_recovery(
        db=db_session,
        recovery=recovery,
        incident=incident,
        service=service,
        simulated_healthy=True,
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
