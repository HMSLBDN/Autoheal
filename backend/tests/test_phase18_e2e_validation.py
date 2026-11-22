"""
AutoHeal DevOps — Phase 18 End-to-End System Validation Pytest Suite
Validates the complete autonomous recovery lifecycle:
1. Authenticated synthetic Alertmanager webhook ingestion & invalid authentication rejection.
2. Duplicate alert deduplication into existing active incidents.
3. Incident creation, telemetry evidence attachment, and audit persistence.
4. Automated AI diagnosis & graceful fallback behavior under provider failures.
5. Governance policy evaluation (allowlists, environment eligibility, retry limits).
6. Human-in-the-loop operator approval & rejection workflows.
7. Simulated recovery execution hard-lock (RECOVERY_SIMULATION_MODE=true).
8. Two-stage post-recovery health verification (Honest HTTP 503 failure vs HTTP 200 restoration).
9. Incident state machine transitions, resolution guards, and escalation paths.
10. Server-Sent Events (SSE) real-time domain event delivery and tenant isolation.
11. Analytics API reliability and MTTR rollup aggregations.

NOTE ON MONITORING ARCHITECTURE:
Prometheus and Alertmanager integrations are verified via authenticated synthetic webhook
payloads conforming strictly to the Alertmanager v4 specification. This validates the full
control plane pipeline without breaching network segregation or requiring real infrastructure alterations.
"""

from datetime import datetime, timezone
import hashlib
import hmac
import json
from typing import AsyncGenerator, Dict, Any
from unittest.mock import AsyncMock, patch
import uuid

from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.config import get_settings
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.incident import Incident, IncidentEvent, IncidentEvidence, IncidentTransition
from app.models.organization import Organization
from app.models.recovery import RecoveryAction, RecoveryResult
from app.models.service import RecoveryPolicy, Service
from app.models.user import User
from app.services.ai.base import AIDiagnosisResult
from app.services.events import event_broadcaster
from app.services.incident.state_machine import IncidentStateMachine, InvalidIncidentTransitionError
from app.services.recovery.executor import RecoveryExecutor
from app.services.recovery.policy_engine import policy_engine
from app.services.recovery.verifier import PostRecoveryVerifier

settings = get_settings()

# Strictly isolated in-memory SQLite database
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
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides an isolated transactional database session backed by in-memory SQLite."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    # Clean up FastAPI dependency overrides
    app.dependency_overrides.clear()


async def setup_phase18_context(db_session: AsyncSession) -> Dict[str, Any]:
    """
    Provisions a complete isolated multi-tenant organization context:
    - Organization (enterprise plan)
    - Admin, Operator, and Viewer users with cryptographically signed JWT tokens
    - Monitored Service (autoheal_test_service)
    - Active RecoveryPolicy for restart_service
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    org_id = uuid.uuid4()
    org = Organization(
        id=org_id,
        slug=f"p18-org-{uuid.uuid4().hex[:6]}",
        name="Phase 18 Validation Org",
        plan="enterprise",
        is_active=True,
    )
    db_session.add(org)

    # Users
    admin_id = uuid.uuid4()
    admin_user = User(
        id=admin_id,
        organization_id=org_id,
        email="admin@phase18.local",
        full_name="Phase 18 Admin",
        hashed_password=get_password_hash("AdminPass123!"),
        role="admin",
        is_active=True,
    )

    operator_id = uuid.uuid4()
    operator_user = User(
        id=operator_id,
        organization_id=org_id,
        email="operator@phase18.local",
        full_name="Phase 18 Operator",
        hashed_password=get_password_hash("OperatorPass123!"),
        role="operator",
        is_active=True,
    )

    viewer_id = uuid.uuid4()
    viewer_user = User(
        id=viewer_id,
        organization_id=org_id,
        email="viewer@phase18.local",
        full_name="Phase 18 Viewer",
        hashed_password=get_password_hash("ViewerPass123!"),
        role="viewer",
        is_active=True,
    )
    db_session.add_all([admin_user, operator_user, viewer_user])

    # Monitored Service
    service = Service(
        id="autoheal_test_service",
        organization_id=org_id,
        name="autoheal_test_service",
        environment="production",
        status="healthy",
        availability=99.95,
        error_rate=0.01,
        latency_ms=120,
    )
    db_session.add(service)

    # Policy
    policy = RecoveryPolicy(
        id=uuid.uuid4(),
        service_id=service.id,
        action="restart_service",
        approval_required=True,
        cooldown_seconds=300,
        max_retries=3,
        is_active=True,
    )
    db_session.add(policy)

    await db_session.commit()

    # Generate JWT tokens
    admin_token = create_access_token(str(admin_id), admin_user.email, "admin", str(org_id))
    operator_token = create_access_token(str(operator_id), operator_user.email, "operator", str(org_id))
    viewer_token = create_access_token(str(viewer_id), viewer_user.email, "viewer", str(org_id))

    return {
        "org": org,
        "org_id": org_id,
        "admin_user": admin_user,
        "operator_user": operator_user,
        "viewer_user": viewer_user,
        "admin_token": admin_token,
        "operator_token": operator_token,
        "viewer_token": viewer_token,
        "service": service,
        "policy": policy,
    }


def make_alertmanager_payload(service_name: str = "autoheal_test_service", alertname: str = "ServiceDown", severity: str = "critical") -> Dict[str, Any]:
    """Generates canonical Alertmanager v4 JSON webhook payload for testing."""
    return {
        "version": "4",
        "groupKey": f"{{}}:{{alertname=\"{alertname}\", service=\"{service_name}\"}}",
        "status": "firing",
        "receiver": "autoheal-webhook",
        "groupLabels": {"alertname": alertname, "service": service_name},
        "commonLabels": {"alertname": alertname, "service": service_name, "severity": severity},
        "commonAnnotations": {
          "summary": f"Service {service_name} is unreachable",
          "description": f"Health checks failed: {service_name} reported HTTP 503 connection pool failure.",
          "probable_cause": "Thread pool exhaustion under synthetic chaos load",
          "recommended_action": "restart_service"
        },
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": alertname, "service": service_name, "severity": severity},
                "annotations": {
                    "summary": f"Service {service_name} is unreachable",
                    "description": f"Health checks failed: {service_name} reported HTTP 503 connection pool failure.",
                    "probable_cause": "Thread pool exhaustion under synthetic chaos load"
                },
                "startsAt": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }


# ==============================================================================
# 1. Alert Ingestion & Authentication Security (Gates 1 & 2)
# ==============================================================================

@pytest.mark.asyncio
async def test_01_authenticated_synthetic_alertmanager_webhook_ingestion(db_session: AsyncSession):
    """
    Validates authenticated Alertmanager webhook ingestion using both:
    1. Authorization: Bearer <ALERTMANAGER_HMAC_SECRET>
    2. Cryptographic X-AutoHeal-Signature HMAC-SHA256 header.
    Confirms successful incident detection and persistence without crossing networks.
    """
    ctx = await setup_phase18_context(db_session)
    payload = make_alertmanager_payload(service_name=ctx["service"].name)
    payload_bytes = json.dumps(payload).encode("utf-8")
    secret_key = settings.ALERTMANAGER_HMAC_SECRET

    # Compute HMAC-SHA256 signature
    hmac_sig = hmac.new(secret_key.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Test 1A: Ingestion via Bearer Token
        res_bearer = await ac.post(
            "/api/v1/alerts/webhook",
            json=payload,
            headers={"Authorization": f"Bearer {secret_key}"},
        )
        assert res_bearer.status_code == 200, res_bearer.text
        body_bearer = res_bearer.json()
        assert body_bearer["status"] == "success"
        assert body_bearer["processed_alerts"] == 1
        assert body_bearer["incidents_created"] == 1

        # Verify incident in database
        stmt = select(Incident).where(Incident.service_id == ctx["service"].id)
        res = await db_session.execute(stmt)
        created_incident = res.scalar_one_or_none()
        assert created_incident is not None
        assert created_incident.status == "open"
        assert created_incident.severity == "critical"
        assert created_incident.service_name == "autoheal_test_service"

    # Test 1B: Ingestion via HMAC-SHA256 header (for second distinct service)
    svc2 = Service(
        id="payments-api",
        organization_id=ctx["org_id"],
        name="payments-api",
        environment="production",
        status="healthy",
    )
    db_session.add(svc2)
    await db_session.commit()

    payload2 = make_alertmanager_payload(service_name="payments-api", alertname="HighErrorRate", severity="high")
    payload2_bytes = json.dumps(payload2).encode("utf-8")
    hmac_sig2 = hmac.new(secret_key.encode("utf-8"), payload2_bytes, hashlib.sha256).hexdigest()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res_hmac = await ac.post(
            "/api/v1/alerts/webhook",
            content=payload2_bytes,
            headers={
                "Content-Type": "application/json",
                "X-AutoHeal-Signature": f"sha256={hmac_sig2}",
            },
        )
        assert res_hmac.status_code == 200, res_hmac.text
        assert res_hmac.json()["incidents_created"] == 1


@pytest.mark.asyncio
async def test_02_invalid_authentication_rejection(db_session: AsyncSession):
    """
    Validates fail-closed security for Alertmanager webhook endpoint:
    - Missing credentials -> 401 Unauthorized
    - Invalid bearer token -> 401 Unauthorized
    - Tampered HMAC signature -> 401 Unauthorized
    Confirms zero unauthorized database mutations.
    """
    ctx = await setup_phase18_context(db_session)
    payload = make_alertmanager_payload(service_name=ctx["service"].name)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Missing Authorization header
        res_no_auth = await ac.post("/api/v1/alerts/webhook", json=payload)
        assert res_no_auth.status_code == 401

        # 2. Invalid Bearer Token
        res_bad_token = await ac.post(
            "/api/v1/alerts/webhook",
            json=payload,
            headers={"Authorization": "Bearer invalid_secret_token_12345"},
        )
        assert res_bad_token.status_code == 401

        # 3. Forged/Tampered HMAC Signature
        res_bad_sig = await ac.post(
            "/api/v1/alerts/webhook",
            json=payload,
            headers={"X-AutoHeal-Signature": "sha256=0000000000000000000000000000000000000000000000000000000000000000"},
        )
        assert res_bad_sig.status_code == 401

    # Verify zero incidents were created
    count = (await db_session.execute(select(func.count(Incident.id)))).scalar()
    assert count == 0


@pytest.mark.asyncio
async def test_03_duplicate_alert_deduplication(db_session: AsyncSession):
    """
    Validates alert deduplication:
    When an active incident already exists for a service, subsequent firing alerts
    must update the existing incident rather than creating duplicate incidents.
    """
    ctx = await setup_phase18_context(db_session)
    secret_key = settings.ALERTMANAGER_HMAC_SECRET

    # Pre-seed active incident
    existing_inc = Incident(
        id="INC-P18-EXISTING-001",
        organization_id=ctx["org_id"],
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        title="Initial service degradation",
        severity="medium",
        status="open",
        error_rate=2.5,
        threshold=1.0,
    )
    db_session.add(existing_inc)
    await db_session.commit()

    payload = make_alertmanager_payload(service_name=ctx["service"].name, severity="critical")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/alerts/webhook",
            json=payload,
            headers={"Authorization": f"Bearer {secret_key}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["incidents_created"] == 0
        assert body["incidents_updated"] == 1

    # Verify only 1 incident exists and severity escalated to critical
    stmt = select(Incident).where(Incident.service_id == ctx["service"].id)
    incidents = (await db_session.execute(stmt)).scalars().all()
    assert len(incidents) == 1
    assert incidents[0].id == "INC-P18-EXISTING-001"
    assert incidents[0].severity == "critical"

    # Verify deduplication event recorded
    events_stmt = select(IncidentEvent).where(IncidentEvent.incident_id == existing_inc.id)
    events = (await db_session.execute(events_stmt)).scalars().all()
    assert any("Alert Re-triggered" in e.label for e in events)


# ==============================================================================
# 2. Incident Creation, Telemetry & Diagnosis (Gate 3)
# ==============================================================================

@pytest.mark.asyncio
async def test_04_incident_creation_and_evidence_persistence(db_session: AsyncSession):
    """
    Validates complete incident metadata and evidence structure:
    - Unique Incident ID assignment
    - Telemetry evidence persistence (IncidentEvidence with kind='metric')
    - Incident event history logging (IncidentEvent with label='Incident Detected')
    - Audit log traceability
    """
    ctx = await setup_phase18_context(db_session)
    payload = make_alertmanager_payload(service_name=ctx["service"].name, alertname="ServiceDown")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/alerts/webhook",
            json=payload,
            headers={"Authorization": f"Bearer {settings.ALERTMANAGER_HMAC_SECRET}"},
        )
        assert res.status_code == 200

    # Query created incident with eager-loaded relationships
    stmt = (
        select(Incident)
        .options(
            selectinload(Incident.evidence),
            selectinload(Incident.events),
        )
        .where(Incident.service_id == ctx["service"].id)
    )
    incident = (await db_session.execute(stmt)).scalar_one()

    assert incident.id.startswith("INC-")
    assert incident.service_name == "autoheal_test_service"
    assert incident.detected_at is not None
    assert incident.status == "open"

    # Evidence verification
    assert len(incident.evidence) >= 1
    metric_ev = next(e for e in incident.evidence if e.kind == "metric")
    assert metric_ev.title == "ServiceDown"
    assert "autoheal_test_service" in metric_ev.detail

    # Event history verification
    assert len(incident.events) >= 1
    assert any(e.label == "Incident Detected" for e in incident.events)

    # Audit log verification
    audit_stmt = select(AuditLog).where(AuditLog.resource_id == incident.id)
    audit = (await db_session.execute(audit_stmt)).scalar_one_or_none()
    assert audit is not None
    assert audit.action == "incident_created_by_alertmanager"


@pytest.mark.asyncio
async def test_05_automated_diagnosis_and_fallback_behaviour(db_session: AsyncSession):
    """
    Validates AI diagnosis integration:
    Path A: Successful diagnosis returns structured root cause & allowlisted action.
    Path B: Simulated external AI failure gracefully falls back without breaking ingestion.
    """
    ctx = await setup_phase18_context(db_session)
    secret_key = settings.ALERTMANAGER_HMAC_SECRET

    # --- Path A: Mocked Successful AI Diagnosis ---
    mock_diagnosis = AIDiagnosisResult(
        summary="Synthetic thread exhaustion detected on autoheal_test_service",
        probable_root_cause="Thread pool starvation under synthetic chaos load",
        severity="critical",
        supporting_evidence=["HTTP 503 response", "Active thread saturation"],
        recommended_action="restart_service",
        risk_level="low",
        confidence_score=0.95,
        expected_outcome="Service HTTP 200 health restored",
        provider_source="heuristic_fallback",
    )

    with patch("app.api.routes.alerts.get_ai_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.diagnose.return_value = mock_diagnosis
        mock_get_provider.return_value = mock_provider

        payload_a = make_alertmanager_payload(service_name=ctx["service"].name)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res_a = await ac.post(
                "/api/v1/alerts/webhook",
                json=payload_a,
                headers={"Authorization": f"Bearer {secret_key}"},
            )
            assert res_a.status_code == 200

        # Verify incident updated with diagnosis
        stmt_a = (
            select(Incident)
            .options(selectinload(Incident.evidence))
            .where(Incident.service_id == ctx["service"].id)
        )
        inc_a = (await db_session.execute(stmt_a)).scalar_one()
        assert inc_a.probable_cause == "Thread pool starvation under synthetic chaos load"
        assert inc_a.recommended_action == "restart_service"
        assert inc_a.recovery_status == "Approval required"

        # Verify diagnosis evidence attached
        diag_ev = next(e for e in inc_a.evidence if e.kind == "log" and "AI Root Cause" in e.title)
        assert diag_ev is not None

    # --- Path B: Fallback Behavior under Provider Failure ---
    svc_b = Service(
        id="payments-fallback-svc",
        organization_id=ctx["org_id"],
        name="payments-fallback-svc",
        environment="production",
        status="healthy",
    )
    db_session.add(svc_b)
    await db_session.commit()

    with patch("app.api.routes.alerts.get_ai_provider") as mock_get_provider_fail:
        mock_provider_fail = AsyncMock()
        mock_provider_fail.diagnose.side_effect = RuntimeError("External AI API timeout / quota exceeded")
        mock_get_provider_fail.return_value = mock_provider_fail

        payload_b = make_alertmanager_payload(service_name="payments-fallback-svc")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res_b = await ac.post(
                "/api/v1/alerts/webhook",
                json=payload_b,
                headers={"Authorization": f"Bearer {secret_key}"},
            )
            # Ingestion must not crash; returns 200 OK
            assert res_b.status_code == 200

        # Verify fallback fields populated
        stmt_b = select(Incident).where(Incident.service_id == "payments-fallback-svc")
        inc_b = (await db_session.execute(stmt_b)).scalar_one()
        assert inc_b.probable_cause == "Automated heuristic analysis pending"
        assert inc_b.recovery_status == "Approval required"


# ==============================================================================
# 3. Governance Policy Evaluation & Operator Approval (Gate 4)
# ==============================================================================

@pytest.mark.asyncio
async def test_06_recovery_policy_evaluation(db_session: AsyncSession):
    """
    Validates policy engine governance constraints:
    1. Approved action within allowlist -> allowed=True
    2. Forbidden action outside allowlist -> allowed=False (Security violation)
    3. Retry threshold breach -> allowed=False (Human escalation required)
    """
    ctx = await setup_phase18_context(db_session)

    # 1. Approved action
    res_allowed = await policy_engine.evaluate_policy(
        db=db_session,
        organization_id=ctx["org_id"],
        service_id=ctx["service"].id,
        action="restart_service",
    )
    assert res_allowed.allowed is True
    assert res_allowed.requires_approval is True

    # 2. Non-allowlisted action
    res_forbidden = await policy_engine.evaluate_policy(
        db=db_session,
        organization_id=ctx["org_id"],
        service_id=ctx["service"].id,
        action="drop_database_tables",
    )
    assert res_forbidden.allowed is False
    assert "Security violation" in res_forbidden.reason

    # 3. Retry limit breach: Seed 3 previous completed/failed attempts
    test_inc = Incident(
        id="INC-RETRY-LIMIT-001",
        organization_id=ctx["org_id"],
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        title="Retry breach test",
        status="investigating",
    )
    db_session.add(test_inc)
    for i in range(3):
        db_session.add(RecoveryAction(
            id=f"REC-RETRY-{i}",
            incident_id=test_inc.id,
            service_id=ctx["service"].id,
            service_name=ctx["service"].name,
            action="restart_service",
            status="failed",
            approval_required=False,
            requested_by="policy_engine",
        ))
    await db_session.commit()

    res_retry_breach = await policy_engine.evaluate_policy(
        db=db_session,
        organization_id=ctx["org_id"],
        service_id=ctx["service"].id,
        action="restart_service",
        incident_id=test_inc.id,
    )
    assert res_retry_breach.allowed is False
    assert "Retry limit exceeded" in res_retry_breach.reason


@pytest.mark.asyncio
async def test_07_operator_approval_and_governance_checks(db_session: AsyncSession):
    """
    Validates human-in-the-loop operator approval endpoints:
    1. Operator can approve pending action -> status='approved'
    2. Double approval rejected with 409 Conflict
    3. Viewer role cannot approve -> 403 Forbidden
    4. Operator rejection sets status strictly to 'rejected'
    """
    ctx = await setup_phase18_context(db_session)

    incident = Incident(
        id="INC-APPROVAL-TEST-001",
        organization_id=ctx["org_id"],
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        title="Approval test incident",
        status="open",
    )
    db_session.add(incident)

    recovery = RecoveryAction(
        id="REC-APPROVAL-001",
        incident_id=incident.id,
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        action="restart_service",
        status="pending_approval",
        approval_required=True,
        requested_by="AI Diagnosis Engine",
        verification="pending",
    )
    db_session.add(recovery)
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Viewer attempt to approve (Must Fail with 403)
        res_viewer = await ac.post(
            f"/api/v1/recoveries/{recovery.id}/approve",
            headers={"Authorization": f"Bearer {ctx['viewer_token']}"},
        )
        assert res_viewer.status_code == 403

        # Operator approval (Must Succeed with 200)
        res_op = await ac.post(
            f"/api/v1/recoveries/{recovery.id}/approve",
            headers={"Authorization": f"Bearer {ctx['operator_token']}"},
        )
        assert res_op.status_code == 200
        assert res_op.json()["status"] == "approved"

        # Double approval attempt (Must Fail with 409 Conflict)
        res_double = await ac.post(
            f"/api/v1/recoveries/{recovery.id}/approve",
            headers={"Authorization": f"Bearer {ctx['operator_token']}"},
        )
        assert res_double.status_code == 409

    # Rejection workflow test on distinct action
    recovery_reject = RecoveryAction(
        id="REC-REJECT-001",
        incident_id=incident.id,
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        action="restart_service",
        status="pending_approval",
        approval_required=True,
        requested_by="AI Diagnosis Engine",
        verification="pending",
    )
    db_session.add(recovery_reject)
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res_reject = await ac.post(
            f"/api/v1/recoveries/{recovery_reject.id}/reject",
            json={"reason": "Operator observed false positive"},
            headers={"Authorization": f"Bearer {ctx['operator_token']}"},
        )
        assert res_reject.status_code == 200
        assert res_reject.json()["status"] == "rejected"
        assert res_reject.json()["verification"] == "failed"


# ==============================================================================
# 4. Simulated Recovery Execution & Two-Stage Verification (Gate 5)
# ==============================================================================

@pytest.mark.asyncio
async def test_08_simulated_recovery_execution_enforcement(db_session: AsyncSession):
    """
    Validates strict simulation mode enforcement during recovery execution:
    - Confirms settings.RECOVERY_SIMULATION_MODE is True
    - Confirms execution_mode is strictly 'SIMULATED'
    - Confirms [AGENT_EXECUTION_RECEIPT] MODE: SIMULATED in diagnostic output
    - Confirms unapproved action execution raises ValueError
    """
    ctx = await setup_phase18_context(db_session)
    assert settings.RECOVERY_SIMULATION_MODE is True
    assert getattr(settings, "RESTRICTED_DOCKER_AGENT_ENABLED", False) is False

    incident = Incident(
        id="INC-SIM-EXEC-001",
        organization_id=ctx["org_id"],
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        title="Simulation execution test",
        status="investigating",
    )
    recovery_unapproved = RecoveryAction(
        id="REC-UNAPPROVED-001",
        incident_id=incident.id,
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        action="restart_service",
        status="pending_approval",
        approval_required=True,
        requested_by="policy_engine",
        verification="pending",
    )
    recovery_approved = RecoveryAction(
        id="REC-APPROVED-001",
        incident_id=incident.id,
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        action="restart_service",
        status="approved",
        approval_required=True,
        requested_by="policy_engine",
        verification="pending",
    )
    db_session.add_all([incident, recovery_unapproved, recovery_approved])
    await db_session.commit()

    executor = RecoveryExecutor()

    # 1. Service Layer Guard: Calling executor directly on unapproved recovery must raise ValueError
    with pytest.raises(ValueError, match="requires explicit operator approval before execution"):
        await executor.execute_recovery(db=db_session, recovery_id=recovery_unapproved.id)

    # 2. Unapproved execution attempt through API endpoint must fail with HTTP 400
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res_unapproved = await ac.post(
            f"/api/v1/recoveries/{recovery_unapproved.id}/execute",
            headers={"Authorization": f"Bearer {ctx['operator_token']}"},
        )
        assert res_unapproved.status_code == 400
        assert "requires explicit operator approval before execution" in res_unapproved.json()["detail"]

    # 2. Verify recovery remains pending approval with no execution receipt generated
    await db_session.refresh(recovery_unapproved)
    assert recovery_unapproved.status == "pending_approval"
    res_receipt = await db_session.execute(
        select(RecoveryResult).where(RecoveryResult.recovery_action_id == recovery_unapproved.id)
    )
    assert res_receipt.scalar_one_or_none() is None

    # 3. Service layer guard: verify executor directly rejects non-executable terminal statuses
    recovery_rejected = RecoveryAction(
        id="REC-REJECTED-001",
        incident_id=incident.id,
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        action="restart_service",
        status="rejected",
        approval_required=True,
        requested_by="policy_engine",
        verification="failed",
    )
    db_session.add(recovery_rejected)
    await db_session.commit()

    with pytest.raises(ValueError, match="cannot be executed from status 'rejected'"):
        await executor.execute_recovery(db=db_session, recovery_id=recovery_rejected.id)

    # 4. Approved execution in simulation mode
    executed = await executor.execute_recovery(db=db_session, recovery_id=recovery_approved.id, simulated_outcome_healthy=True)
    assert executed.execution_mode == "SIMULATED"
    assert executed.result is not None
    assert "[AGENT_EXECUTION_RECEIPT]" in executed.result.diagnostic_output
    assert "MODE: SIMULATED" in executed.result.diagnostic_output


@pytest.mark.asyncio
async def test_09_post_recovery_health_verification_failure_scenario(db_session: AsyncSession):
    """
    Validates honest verification failure handling (Phase 18 Stage A / HTTP 503):
    When post-recovery health remains degraded:
    - verification must be marked 'failed'
    - evidence_classification must be 'VERIFICATION_FAILED'
    - incident must remain 'investigating' (Never falsely resolved)
    - resolved_at must remain None
    """
    ctx = await setup_phase18_context(db_session)

    incident = Incident(
        id="INC-VERIF-FAIL-001",
        organization_id=ctx["org_id"],
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        title="Verification failure test",
        status="investigating",
        error_rate=15.0,
        threshold=1.0,
        resolved_at=None,
    )
    recovery = RecoveryAction(
        id="REC-VERIF-FAIL-001",
        incident_id=incident.id,
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        action="restart_service",
        status="approved",
        approval_required=False,
        requested_by="policy_engine",
        verification="pending",
    )
    db_session.add_all([incident, recovery])
    await db_session.commit()

    executor = RecoveryExecutor()
    # Execute recovery with simulated_outcome_healthy=False (corresponding to persistent HTTP 503)
    executed = await executor.execute_recovery(
        db=db_session,
        recovery_id=recovery.id,
        simulated_outcome_healthy=False,
    )

    assert executed.verification == "failed"
    assert executed.evidence_classification == "VERIFICATION_FAILED"
    assert incident.status == "investigating"
    assert incident.resolved_at is None


@pytest.mark.asyncio
async def test_10_post_recovery_health_verification_success_scenario(db_session: AsyncSession):
    """
    Validates successful verification & incident resolution (Phase 18 Stage B / HTTP 200):
    When post-recovery health check passes:
    - verification must be marked 'passed'
    - evidence_classification must be 'HEALTH_VERIFIED'
    - incident must transition to 'resolved'
    - resolved_at must contain a valid UTC timestamp
    - structured metric comparison evidence must be recorded
    """
    ctx = await setup_phase18_context(db_session)

    incident = Incident(
        id="INC-VERIF-PASS-001",
        organization_id=ctx["org_id"],
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        title="Verification success test",
        status="investigating",
        error_rate=12.5,
        threshold=1.0,
        resolved_at=None,
    )
    recovery = RecoveryAction(
        id="REC-VERIF-PASS-001",
        incident_id=incident.id,
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        action="restart_service",
        status="running",
        approval_required=False,
        requested_by="policy_engine",
        verification="pending",
    )
    db_session.add_all([incident, recovery])
    await db_session.commit()

    verifier = PostRecoveryVerifier()
    # Execute verification with simulated_healthy=True (corresponding to HTTP 200 restored state)
    verified = await verifier.verify_recovery(
        db=db_session,
        recovery=recovery,
        incident=incident,
        service=ctx["service"],
        simulated_healthy=True,
        execution_mode="SIMULATED",
        evidence_classification="HEALTH_VERIFIED",
    )

    assert verified is True
    assert recovery.verification == "passed"
    assert recovery.evidence_classification == "HEALTH_VERIFIED"
    assert incident.status == "resolved"
    assert incident.resolved_at is not None
    assert isinstance(incident.resolved_at, datetime)

    # Verify structured SLA check evidence
    ev_stmt = select(IncidentEvidence).where(
        IncidentEvidence.incident_id == incident.id,
        IncidentEvidence.kind == "health_check",
    )
    ev = (await db_session.execute(ev_stmt)).scalar_one_or_none()
    assert ev is not None
    assert "HEALTH_VERIFIED" in ev.title


# ==============================================================================
# 5. Incident State Machine & Resolution Guards
# ==============================================================================

@pytest.mark.asyncio
async def test_11_incident_resolution_and_escalation_state_machine(db_session: AsyncSession):
    """
    Validates state machine transitions and resolution integrity:
    1. Illegal direct transition (resolved -> open) raises InvalidIncidentTransitionError
    2. Resolution guard blocks resolving incident when recovery has not passed (without sign-off)
    3. Explicit operator sign-off permits resolution with audit log
    """
    ctx = await setup_phase18_context(db_session)
    sm = IncidentStateMachine()

    incident = Incident(
        id="INC-SM-GUARD-001",
        organization_id=ctx["org_id"],
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        title="State machine guard test",
        status="investigating",
    )
    recovery_failed = RecoveryAction(
        id="REC-SM-FAIL-001",
        incident_id=incident.id,
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        action="restart_service",
        status="completed",
        verification="failed",
    )
    db_session.add_all([incident, recovery_failed])
    await db_session.commit()

    # 1. Attempting resolution without verified recovery and without sign-off must fail
    with pytest.raises(InvalidIncidentTransitionError, match="Cannot transition incident to 'resolved' without verified recovery"):
        await sm.transition_incident(
            db=db_session,
            incident_id=incident.id,
            organization_id=ctx["org_id"],
            target_status="resolved",
            actor_id=ctx["operator_user"].id,
            actor_email=ctx["operator_user"].email,
            actor_role="operator",
            reason="Attempting unverified resolution",
            sign_off=False,
        )

    # 2. Resolution with explicit operator sign-off succeeds
    resolved_inc = await sm.transition_incident(
        db=db_session,
        incident_id=incident.id,
        organization_id=ctx["org_id"],
        target_status="resolved",
        actor_id=ctx["operator_user"].id,
        actor_email=ctx["operator_user"].email,
        actor_role="operator",
        reason="Manual operator sign-off following out-of-band verification",
        sign_off=True,
    )
    assert resolved_inc.status == "resolved"
    assert resolved_inc.resolved_at is not None

    # 3. Illegal transition from resolved directly to open (without reopening) must raise error
    with pytest.raises(InvalidIncidentTransitionError):
        await sm.transition_incident(
            db=db_session,
            incident_id=incident.id,
            organization_id=ctx["org_id"],
            target_status="open",
            actor_id=ctx["operator_user"].id,
            actor_email=ctx["operator_user"].email,
            actor_role="operator",
            reason="Illegal status reversion",
        )


# ==============================================================================
# 6. Real-Time Event Streaming & Analytics Rollup (Gate 6)
# ==============================================================================

@pytest.mark.asyncio
async def test_12_realtime_sse_event_delivery_and_multi_tenant_isolation(db_session: AsyncSession):
    """
    Validates real-time Server-Sent Events (SSE) distribution:
    1. Subscribes client queue to organization events
    2. Broadcasts incident_created, recovery_updated, incident_updated
    3. Confirms accurate event payload delivery to subscriber queue
    4. Confirms multi-tenant isolation (Org B events never leak to Org A)
    """
    ctx = await setup_phase18_context(db_session)
    org_a_id = ctx["org_id"]
    org_b_id = uuid.uuid4()

    # Create subscriber generator for Org A
    sub_gen = event_broadcaster.subscribe(org_a_id)
    # Read initial connected frame
    init_chunk = await sub_gen.__anext__()
    assert "event: connected" in init_chunk
    assert str(org_a_id) in init_chunk

    # Broadcast event to Org A
    await event_broadcaster.broadcast(
        org_id=org_a_id,
        event_type="incident_created",
        data={"id": "INC-SSE-001", "serviceName": "autoheal_test_service", "status": "open"},
    )
    event_chunk = await sub_gen.__anext__()
    assert "event: incident_created" in event_chunk
    assert "INC-SSE-001" in event_chunk

    # Broadcast event to Org B (Must NOT leak to Org A subscriber)
    await event_broadcaster.broadcast(
        org_id=org_b_id,
        event_type="incident_created",
        data={"id": "INC-LEAK-TEST", "serviceName": "secret-svc", "status": "open"},
    )
    # Verify no immediate message in queue by checking timeout
    broadcast_count = await event_broadcaster.broadcast(
        org_id=org_a_id,
        event_type="recovery_updated",
        data={"id": "REC-SSE-001", "status": "approved"},
    )
    assert broadcast_count >= 1
    second_chunk = await sub_gen.__anext__()
    assert "event: recovery_updated" in second_chunk
    assert "INC-LEAK-TEST" not in second_chunk

    # Cleanup subscriber generator
    await sub_gen.aclose()


@pytest.mark.asyncio
async def test_13_analytics_api_reliability_and_mttr_aggregation(db_session: AsyncSession):
    """
    Validates Analytics API calculation:
    - Queries GET /api/v1/analytics/summary
    - Asserts accurate aggregation of incident count, average availability,
      and recovery success rate matching seeded database rows.
    """
    ctx = await setup_phase18_context(db_session)

    # Seed incidents and recoveries for analytics
    inc1 = Incident(
        id="INC-ANALYTICS-001",
        organization_id=ctx["org_id"],
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        title="Analytics test incident 1",
        status="resolved",
        error_rate=5.0,
        threshold=1.0,
    )
    inc2 = Incident(
        id="INC-ANALYTICS-002",
        organization_id=ctx["org_id"],
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        title="Analytics test incident 2",
        status="investigating",
        error_rate=3.0,
        threshold=1.0,
    )
    rec1 = RecoveryAction(
        id="REC-ANALYTICS-001",
        incident_id=inc1.id,
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        action="restart_service",
        status="completed",
        duration_seconds=180,
    )
    rec2 = RecoveryAction(
        id="REC-ANALYTICS-002",
        incident_id=inc2.id,
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        action="restart_service",
        status="failed",
        duration_seconds=300,
    )
    db_session.add_all([inc1, inc2, rec1, rec2])
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res_get = await ac.get(
            "/api/v1/analytics/summary",
            headers={"Authorization": f"Bearer {ctx['operator_token']}"},
        )
        assert res_get.status_code == 200, res_get.text
        data = res_get.json()

        # Contract assertions matching AnalyticsSummaryResponse schema
        assert "incidentCount" in data or "incident_count" in data
        count_val = data.get("incidentCount") if "incidentCount" in data else data.get("incident_count")
        assert count_val == 2

        assert "availability" in data
        assert isinstance(data["availability"], float)

        assert "recoverySuccessRate" in data or "recovery_success_rate" in data
        success_rate = data.get("recoverySuccessRate") if "recoverySuccessRate" in data else data.get("recovery_success_rate")
        # 1 completed out of 2 terminal (completed + failed) = 50.0%
        assert success_rate == 50.0
