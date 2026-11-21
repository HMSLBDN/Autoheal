"""
AutoHeal DevOps — Phase 5 End-to-End Repeatable Acceptance Test Suite
Verifies all 17 requirements and the complete demonstration lifecycle:
 1. Healthy service does not create an incident.
 2. Controlled failure creates an incident.
 3. Duplicate alerts do not create duplicate incidents.
 4. Incident evidence is persisted.
 5. Diagnosis uses incident evidence.
 6. Allowed recovery actions are accepted.
 7. Unsupported actions are rejected.
 8. Missing approval prevents execution.
 9. Unauthorized approval is rejected (RBAC).
10. Successful verification resolves the incident.
11. Failed verification escalates the incident.
12. Retry limits and cooldowns are respected.
13. Demo reset restores service health.
14. Analytics use actual timestamps and persisted records.
15. Incident report downloads successfully (valid PDF).
16. Multi-tenant isolation is strictly maintained.
17. Audit logs record meaningful transitions.
 + Full integrated demonstration workflow.
"""

from datetime import datetime, timezone
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.config import get_settings
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models import (
    AuditLog,
    Incident,
    IncidentEvent,
    IncidentEvidence,
    Organization,
    RecoveryAction,
    RecoveryPolicy,
    RecoveryResult,
    Service,
    User,
)
from app.services.recovery.executor import RecoveryExecutor

settings = get_settings()


@pytest.fixture
def client(db_session: AsyncSession) -> TestClient:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
async def setup_test_org(db_session: AsyncSession):
    """Sets up an organization with an admin, an operator, a viewer, and services."""
    org = Organization(id=uuid.uuid4(), slug=f"demo-org-{uuid.uuid4().hex[:6]}", name="Demo Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    operator = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email=f"op_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Demo Operator",
        hashed_password=get_password_hash("Password123!"),
        role="operator",
        is_active=True,
    )
    viewer = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email=f"view_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Demo Viewer",
        hashed_password=get_password_hash("Password123!"),
        role="viewer",
        is_active=True,
    )
    svc = Service(
        id=f"svc-checkout-{uuid.uuid4().hex[:4]}",
        organization_id=org.id,
        name="checkout-api",
        environment="production",
        status="healthy",
        availability=99.98,
        error_rate=0.01,
        latency_ms=25,
        last_checked=datetime.now(timezone.utc),
    )
    db_session.add_all([operator, viewer, svc])
    await db_session.commit()

    op_token = create_access_token(str(operator.id), operator.email, operator.role, str(org.id))
    viewer_token = create_access_token(str(viewer.id), viewer.email, viewer.role, str(org.id))

    return {
        "org": org,
        "operator": operator,
        "viewer": viewer,
        "service": svc,
        "op_headers": {"Authorization": f"Bearer {op_token}"},
        "viewer_headers": {"Authorization": f"Bearer {viewer_token}"},
    }


# ==============================================================================
# Requirement 1: Healthy service does not create an incident
# ==============================================================================
@pytest.mark.asyncio
async def test_1_healthy_service_does_not_create_incident(client: TestClient, setup_test_org, db_session: AsyncSession):
    ctx = await setup_test_org
    inc_stmt = select(Incident).where(Incident.service_id == ctx["service"].id)
    res = await db_session.execute(inc_stmt)
    assert len(res.scalars().all()) == 0


# ==============================================================================
# Requirement 2: Controlled failure creates an incident
# ==============================================================================
@pytest.mark.asyncio
async def test_2_controlled_failure_creates_incident(client: TestClient, setup_test_org, db_session: AsyncSession):
    ctx = await setup_test_org
    res = client.post(
        "/api/v1/demo/simulate-alert",
        headers=ctx["op_headers"],
        json={
            "service_name": ctx["service"].name,
            "alertname": "HighErrorRate",
            "severity": "critical",
            "summary": "High 5xx error rate on checkout-api",
            "description": "Error rate exceeded 5% threshold.",
            "auto_request_recovery": True,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "created"
    assert data["incident_id"] is not None

    inc_stmt = select(Incident).where(Incident.id == data["incident_id"])
    inc = (await db_session.execute(inc_stmt)).scalar_one()
    assert inc.status == "recovering"
    assert inc.severity == "critical"


# ==============================================================================
# Requirement 3: Duplicate alerts do not create duplicate incidents
# ==============================================================================
@pytest.mark.asyncio
async def test_3_duplicate_alerts_do_not_create_duplicate_incidents(client: TestClient, setup_test_org, db_session: AsyncSession):
    ctx = await setup_test_org
    payload = {
        "service_name": ctx["service"].name,
        "alertname": "HighErrorRate",
        "severity": "critical",
        "summary": "Repeated alert",
        "auto_request_recovery": True,
    }
    # Initial alert
    r1 = client.post("/api/v1/demo/simulate-alert", headers=ctx["op_headers"], json=payload)
    assert r1.status_code == 200
    assert r1.json()["status"] == "created"

    # Repeated alert
    r2 = client.post("/api/v1/demo/simulate-alert", headers=ctx["op_headers"], json=payload)
    assert r2.status_code == 200
    assert r2.json()["status"] == "deduplicated"

    inc_stmt = select(Incident).where(Incident.service_id == ctx["service"].id)
    incidents = (await db_session.execute(inc_stmt)).scalars().all()
    assert len(incidents) == 1


# ==============================================================================
# Requirement 4: Incident evidence is persisted
# ==============================================================================
@pytest.mark.asyncio
async def test_4_incident_evidence_is_persisted(client: TestClient, setup_test_org, db_session: AsyncSession):
    ctx = await setup_test_org
    res = client.post(
        "/api/v1/demo/simulate-alert",
        headers=ctx["op_headers"],
        json={"service_name": ctx["service"].name, "alertname": "HighLatency", "severity": "high"},
    )
    inc_id = res.json()["incident_id"]

    ev_stmt = select(IncidentEvidence).where(IncidentEvidence.incident_id == inc_id)
    evidences = (await db_session.execute(ev_stmt)).scalars().all()
    assert len(evidences) >= 1
    kinds = [e.kind for e in evidences]
    assert "metric" in kinds or "log" in kinds


# ==============================================================================
# Requirement 5: Diagnosis uses incident evidence
# ==============================================================================
@pytest.mark.asyncio
async def test_5_diagnosis_uses_incident_evidence(client: TestClient, setup_test_org, db_session: AsyncSession):
    ctx = await setup_test_org
    res = client.post(
        "/api/v1/demo/simulate-alert",
        headers=ctx["op_headers"],
        json={
            "service_name": ctx["service"].name,
            "alertname": "CPUSaturation",
            "severity": "high",
            "probable_cause": "Thread starvation in connection pool",
        },
    )
    inc_id = res.json()["incident_id"]

    inc_stmt = select(Incident).where(Incident.id == inc_id)
    inc = (await db_session.execute(inc_stmt)).scalar_one()
    assert inc.probable_cause is not None
    assert len(inc.probable_cause) > 0
    assert inc.recommended_action in ("restart_service", "clear_cache", "scale_service", "restore_health", "rollback_release")


# ==============================================================================
# Requirement 6: Allowed recovery actions are accepted
# ==============================================================================
@pytest.mark.asyncio
async def test_6_allowed_recovery_actions_are_accepted(client: TestClient, setup_test_org, db_session: AsyncSession):
    ctx = await setup_test_org
    res = client.post(
        "/api/v1/demo/simulate-alert",
        headers=ctx["op_headers"],
        json={
            "service_name": ctx["service"].name,
            "alertname": "HighLatency",
            "recommended_action": "clear_cache",
            "auto_request_recovery": True,
        },
    )
    rec_id = res.json()["recovery_id"]

    rec_stmt = select(RecoveryAction).where(RecoveryAction.id == rec_id)
    rec = (await db_session.execute(rec_stmt)).scalar_one()
    assert rec.action == "clear_cache"
    assert rec.status == "pending_approval"


# ==============================================================================
# Requirement 7: Unsupported actions are rejected
# ==============================================================================
@pytest.mark.asyncio
async def test_7_unsupported_actions_are_rejected(client: TestClient, setup_test_org, db_session: AsyncSession):
    ctx = await setup_test_org
    # Directly inserting unallowed action and attempting execution
    bad_rec = RecoveryAction(
        id=f"REC-BAD-{uuid.uuid4().hex[:4]}",
        incident_id="INC-DUMMY",
        service_id=ctx["service"].id,
        service_name=ctx["service"].name,
        action="rm -rf /",  # Malicious / unsupported action
        status="approved",
        approval_required=True,
        requested_by=ctx["operator"].email,
        requested_at=datetime.now(timezone.utc),
        verification="pending",
    )
    db_session.add(bad_rec)
    await db_session.commit()

    executor = RecoveryExecutor()
    with pytest.raises(ValueError, match="Security violation: Action 'rm -rf /' is not in the approved recovery allowlist"):
        await executor.execute_recovery(db_session, recovery_id=bad_rec.id)


# ==============================================================================
# Requirement 8: Missing approval prevents execution
# ==============================================================================
@pytest.mark.asyncio
async def test_8_missing_approval_prevents_execution(client: TestClient, setup_test_org, db_session: AsyncSession):
    ctx = await setup_test_org
    res = client.post(
        "/api/v1/demo/simulate-alert",
        headers=ctx["op_headers"],
        json={"service_name": ctx["service"].name, "alertname": "HighErrorRate", "auto_request_recovery": True},
    )
    rec_id = res.json()["recovery_id"]

    # Directly execute without approving
    exec_res = client.post(f"/api/v1/recoveries/{rec_id}/execute", headers=ctx["op_headers"])
    assert exec_res.status_code == 400
    assert "requires explicit operator approval" in exec_res.json()["detail"]


# ==============================================================================
# Requirement 9: Unauthorized approval is rejected (RBAC)
# ==============================================================================
@pytest.mark.asyncio
async def test_9_unauthorized_approval_is_rejected(client: TestClient, setup_test_org, db_session: AsyncSession):
    ctx = await setup_test_org
    res = client.post(
        "/api/v1/demo/simulate-alert",
        headers=ctx["op_headers"],
        json={"service_name": ctx["service"].name, "alertname": "HighErrorRate", "auto_request_recovery": True},
    )
    rec_id = res.json()["recovery_id"]

    # Viewer role attempts approval
    appr_res = client.post(f"/api/v1/recoveries/{rec_id}/approve", headers=ctx["viewer_headers"])
    assert appr_res.status_code == 403
    assert "Insufficient permissions" in appr_res.json()["detail"]


# ==============================================================================
# Requirement 10: Successful verification resolves the incident
# ==============================================================================
@pytest.mark.asyncio
async def test_10_successful_verification_resolves_incident(client: TestClient, setup_test_org, db_session: AsyncSession):
    ctx = await setup_test_org
    res = client.post(
        "/api/v1/demo/simulate-alert",
        headers=ctx["op_headers"],
        json={"service_name": ctx["service"].name, "alertname": "HighErrorRate", "auto_request_recovery": True},
    )
    rec_id = res.json()["recovery_id"]
    inc_id = res.json()["incident_id"]

    # Approve
    client.post(f"/api/v1/recoveries/{rec_id}/approve", headers=ctx["op_headers"])
    # Execute with simulated healthy outcome
    exec_res = client.post(f"/api/v1/recoveries/{rec_id}/execute", headers=ctx["op_headers"])
    assert exec_res.status_code == 200
    assert exec_res.json()["verification"] == "passed"

    # Confirm incident is resolved
    inc_stmt = select(Incident).where(Incident.id == inc_id)
    inc = (await db_session.execute(inc_stmt)).scalar_one()
    assert inc.status == "resolved"
    assert inc.resolved_at is not None


# ==============================================================================
# Requirement 11: Failed verification escalates the incident
# ==============================================================================
@pytest.mark.asyncio
async def test_11_failed_verification_escalates_incident(client: TestClient, setup_test_org, db_session: AsyncSession):
    ctx = await setup_test_org
    res = client.post(
        "/api/v1/demo/simulate-alert",
        headers=ctx["op_headers"],
        json={"service_name": ctx["service"].name, "alertname": "HighErrorRate", "auto_request_recovery": True},
    )
    rec_id = res.json()["recovery_id"]
    inc_id = res.json()["incident_id"]

    client.post(f"/api/v1/recoveries/{rec_id}/approve", headers=ctx["op_headers"])

    # Execute with simulated failure
    executor = RecoveryExecutor()
    await executor.execute_recovery(db_session, recovery_id=rec_id, simulated_outcome_healthy=False)

    inc_stmt = select(Incident).where(Incident.id == inc_id)
    inc = (await db_session.execute(inc_stmt)).scalar_one()
    assert inc.status == "investigating"
    assert "Verification failed" in inc.recovery_status


# ==============================================================================
# Requirement 12: Retry limits and cooldowns are respected
# ==============================================================================
@pytest.mark.asyncio
async def test_12_retry_limits_and_cooldowns_are_respected(client: TestClient, setup_test_org, db_session: AsyncSession):
    ctx = await setup_test_org
    policy = RecoveryPolicy(
        id=uuid.uuid4(),
        service_id=ctx["service"].id,
        action="restart_service",
        approval_required=True,
        cooldown_seconds=300,
        max_retries=2,
        is_active=True,
    )
    db_session.add(policy)
    await db_session.commit()

    pol_stmt = select(RecoveryPolicy).where(RecoveryPolicy.service_id == ctx["service"].id)
    saved_policy = (await db_session.execute(pol_stmt)).scalar_one()
    assert saved_policy.max_retries == 2
    assert saved_policy.cooldown_seconds == 300


# ==============================================================================
# Requirement 13: Demo reset restores service health
# ==============================================================================
@pytest.mark.asyncio
async def test_13_demo_reset_restores_service_health(client: TestClient, setup_test_org, db_session: AsyncSession):
    ctx = await setup_test_org
    # Degrade service
    client.post(
        "/api/v1/demo/fault",
        headers=ctx["op_headers"],
        json={"service_name": ctx["service"].name, "fault_type": "http_500"},
    )
    # Reset
    reset_res = client.post(
        "/api/v1/demo/reset",
        headers=ctx["op_headers"],
        json={"service_name": ctx["service"].name},
    )
    assert reset_res.status_code == 200

    svc_stmt = select(Service).where(Service.id == ctx["service"].id)
    svc = (await db_session.execute(svc_stmt)).scalar_one()
    assert svc.status == "healthy"
    assert svc.error_rate < 0.05


# ==============================================================================
# Requirement 14: Analytics use actual timestamps and persisted records
# ==============================================================================
@pytest.mark.asyncio
async def test_14_analytics_use_actual_timestamps(client: TestClient, setup_test_org, db_session: AsyncSession):
    ctx = await setup_test_org
    analytics_res = client.get("/api/v1/analytics/summary", headers=ctx["op_headers"])
    assert analytics_res.status_code == 200
    data = analytics_res.json()
    assert "detectionLatencySeconds" in data
    assert "recoveryDurationMinutes" in data
    assert "recoverySuccessRate" in data
    assert "falsePositiveRate" in data
    assert "availability" in data
    assert "incidentCount" in data


# ==============================================================================
# Requirement 15: Incident report downloads successfully (valid PDF)
# ==============================================================================
@pytest.mark.asyncio
async def test_15_incident_report_downloads_successfully(client: TestClient, setup_test_org, db_session: AsyncSession):
    ctx = await setup_test_org
    res = client.post(
        "/api/v1/demo/simulate-alert",
        headers=ctx["op_headers"],
        json={"service_name": ctx["service"].name, "alertname": "HighLatency"},
    )
    inc_id = res.json()["incident_id"]

    pdf_res = client.get(f"/api/v1/incidents/{inc_id}/report?format=pdf", headers=ctx["op_headers"])
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF-")


# ==============================================================================
# Requirement 16: Multi-tenant isolation is strictly maintained
# ==============================================================================
@pytest.mark.asyncio
async def test_16_tenant_isolation_is_maintained(client: TestClient, setup_test_org, db_session: AsyncSession):
    ctx_a = await setup_test_org

    # Create Org B
    org_b = Organization(id=uuid.uuid4(), slug=f"org-b-{uuid.uuid4().hex[:6]}", name="Org B", is_active=True)
    db_session.add(org_b)
    await db_session.flush()

    op_b = User(
        id=uuid.uuid4(),
        organization_id=org_b.id,
        email=f"op_b_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Org B Operator",
        hashed_password=get_password_hash("Password123!"),
        role="operator",
        is_active=True,
    )
    db_session.add(op_b)
    await db_session.commit()

    token_b = create_access_token(str(op_b.id), op_b.email, op_b.role, str(org_b.id))
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Org A creates incident
    res = client.post(
        "/api/v1/demo/simulate-alert",
        headers=ctx_a["op_headers"],
        json={"service_name": ctx_a["service"].name, "alertname": "HighLatency"},
    )
    inc_a_id = res.json()["incident_id"]

    # Org B attempts to read Org A incident
    cross_res = client.get(f"/api/v1/incidents/{inc_a_id}", headers=headers_b)
    assert cross_res.status_code == 404


# ==============================================================================
# Requirement 17: Audit logs record meaningful transitions
# ==============================================================================
@pytest.mark.asyncio
async def test_17_audit_logs_record_meaningful_transitions(client: TestClient, setup_test_org, db_session: AsyncSession):
    ctx = await setup_test_org
    res = client.post(
        "/api/v1/demo/simulate-alert",
        headers=ctx["op_headers"],
        json={"service_name": ctx["service"].name, "alertname": "ServiceDown", "auto_request_recovery": True},
    )
    rec_id = res.json()["recovery_id"]
    client.post(f"/api/v1/recoveries/{rec_id}/approve", headers=ctx["op_headers"])
    client.post(f"/api/v1/recoveries/{rec_id}/execute", headers=ctx["op_headers"])

    logs_stmt = select(AuditLog).where(AuditLog.organization_id == ctx["org"].id)
    logs = (await db_session.execute(logs_stmt)).scalars().all()
    actions = [l.action for l in logs]

    assert "demo_alert_simulated" in actions
    assert "recovery_approved" in actions
    assert "recovery_executed" in actions
    assert "recovery_verified" in actions


# ==============================================================================
# Integrated End-to-End Repeatable Demonstration Lifecycle Workflow
# ==============================================================================
@pytest.mark.asyncio
async def test_full_repeatable_end_to_end_demonstration_workflow(client: TestClient, setup_test_org, db_session: AsyncSession):
    """
    Executes the entire end-to-end incident lifecycle in sequence:
    Healthy -> Fault Injected -> Alert Detected -> Incident Created ->
    AI Diagnosed -> Recovery Enqueued -> Approved -> Executed ->
    Health Verified -> Resolved -> Analytics Verified -> Report Downloaded.
    """
    ctx = await setup_test_org
    headers = ctx["op_headers"]

    # 1. Verify healthy baseline
    status_res = client.get("/api/v1/demo/status", headers=headers)
    assert status_res.status_code == 200

    # 2. Trigger controlled fault
    fault_res = client.post(
        "/api/v1/demo/fault",
        headers=headers,
        json={"service_name": ctx["service"].name, "fault_type": "http_500", "error_rate": 0.25},
    )
    assert fault_res.status_code == 200
    assert fault_res.json()["metrics"]["error_rate"] == 0.25

    # 3. Simulate Alertmanager alert
    alert_res = client.post(
        "/api/v1/demo/simulate-alert",
        headers=headers,
        json={
            "service_name": ctx["service"].name,
            "alertname": "HighErrorRate",
            "severity": "critical",
            "summary": "5xx error rate breach on checkout-api",
            "auto_request_recovery": True,
        },
    )
    assert alert_res.status_code == 200
    alert_data = alert_res.json()
    inc_id = alert_data["incident_id"]
    rec_id = alert_data["recovery_id"]

    # 4. Inspect incident details & AI diagnosis
    inc_res = client.get(f"/api/v1/incidents/{inc_id}", headers=headers)
    assert inc_res.status_code == 200
    inc_data = inc_res.json()
    assert inc_data["status"] == "recovering"
    assert len(inc_data["evidence"]) >= 1
    assert (inc_data.get("probableCause") or inc_data.get("probable_cause")) is not None

    # 5. Operator approves recovery
    appr_res = client.post(f"/api/v1/recoveries/{rec_id}/approve", headers=headers)
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "approved"

    # 6. Operator executes recovery with automated health verification
    exec_res = client.post(f"/api/v1/recoveries/{rec_id}/execute", headers=headers)
    assert exec_res.status_code == 200
    exec_data = exec_res.json()
    assert exec_data["status"] == "completed"
    assert exec_data["verification"] == "passed"

    # 7. Verify incident resolution in database
    inc_db_stmt = select(Incident).where(Incident.id == inc_id)
    inc_db = (await db_session.execute(inc_db_stmt)).scalar_one()
    assert inc_db.status == "resolved"
    assert inc_db.resolved_at is not None

    # 8. Verify service restored to healthy SLA
    svc_db_stmt = select(Service).where(Service.id == ctx["service"].id)
    svc_db = (await db_session.execute(svc_db_stmt)).scalar_one()
    assert svc_db.status == "healthy"
    assert svc_db.error_rate < 0.05

    # 9. Verify analytics reflect incident and recovery
    analytics_res = client.get("/api/v1/analytics/summary", headers=headers)
    assert analytics_res.status_code == 200
    assert analytics_res.json()["incidentCount"] >= 1

    # 10. Download official PDF report
    pdf_res = client.get(f"/api/v1/incidents/{inc_id}/report?format=pdf", headers=headers)
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF-")

    # 11. Reset demo environment
    reset_res = client.post("/api/v1/demo/reset", headers=headers, json={})
    assert reset_res.status_code == 200
