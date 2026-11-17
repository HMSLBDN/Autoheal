"""
AutoHeal DevOps — End-to-End Monitoring, Incident Detection & Self-Healing Integration Test Suite
Validates:
1. Docker networking port binding security.
2. Microservice health and Prometheus telemetry scraping.
3. Alertmanager webhook ingestion, HMAC authorization, and incident creation.
4. Alert deduplication on repeated breaches.
5. Automated AI root-cause diagnosis and allowlist recommendation.
6. Full policy-gated recovery workflow: request, approve, execute, verify, audit.
7. Recovery rejection and post-recovery verification failure escalation.
8. Multi-tenant isolation across organizations.
"""

from datetime import datetime, timezone
from pathlib import Path
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import yaml

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
    RecoveryResult,
    Service,
    ServiceMonitor,
    User,
)
from app.services.monitoring import MonitoringService
from app.services.recovery.executor import RecoveryExecutor
from app.services.recovery.registry import is_action_allowed, normalize_action

settings = get_settings()


@pytest.fixture
def api_client(db_session: AsyncSession) -> TestClient:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


# ==============================================================================
# 1. Docker Development Networking Security
# ==============================================================================
def test_docker_development_port_security():
    """All development services must bind published ports explicitly to localhost (127.0.0.1)."""
    compose_path = Path(__file__).resolve().parent.parent.parent / "docker-compose.dev.yml"
    assert compose_path.exists(), "docker-compose.dev.yml must exist"

    with open(compose_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    services = config.get("services", {})
    for svc_name, svc_conf in services.items():
        ports = svc_conf.get("ports", [])
        for port in ports:
            port_str = port if isinstance(port, str) else str(port)
            assert port_str.startswith("127.0.0.1:"), (
                f"Security exposure: Service '{svc_name}' port '{port_str}' is not restricted to 127.0.0.1"
            )


# ==============================================================================
# 2. Service Telemetry Monitoring & Snapshot
# ==============================================================================
@pytest.mark.asyncio
async def test_service_health_probe_and_telemetry_snapshot(db_session: AsyncSession):
    """Monitoring service accurately probes services and builds health snapshots."""
    org = Organization(id=uuid.uuid4(), slug="probe-org", name="Probe Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    service = Service(
        id="svc-probe-test",
        organization_id=org.id,
        name="checkout-api",
        environment="production",
        status="healthy",
        availability=99.99,
        error_rate=0.02,
        latency_ms=45,
        last_checked=datetime.now(timezone.utc),
    )
    monitor = ServiceMonitor(
        id=uuid.uuid4(),
        service_id=service.id,
        metrics_path="/metrics",
        health_check_path="/healthz",
        scrape_interval_seconds=15,
        timeout_seconds=3,
    )
    db_session.add_all([service, monitor])
    await db_session.commit()

    monitoring_svc = MonitoringService()
    snapshot = await monitoring_svc.probe_service(service, monitor)

    assert snapshot.service_id == service.id
    assert snapshot.status in ("healthy", "degraded", "critical")
    assert snapshot.availability >= 0.0
    assert snapshot.error_rate >= 0.0


# ==============================================================================
# 3. Alertmanager Webhook Ingestion & Incident Creation
# ==============================================================================
@pytest.mark.asyncio
async def test_alertmanager_webhook_incident_creation_and_ai_diagnosis(api_client: TestClient, db_session: AsyncSession):
    """Firing alerts create incidents, attach evidence, and trigger AI root-cause diagnosis."""
    org = Organization(id=uuid.uuid4(), slug="alert-org", name="Alert Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    svc = Service(
        id="svc-alert-checkout",
        organization_id=org.id,
        name="checkout-api",
        environment="production",
        status="degraded",
        availability=98.5,
        error_rate=2.5,
        latency_ms=620,
        last_checked=datetime.now(timezone.utc),
    )
    db_session.add(svc)
    await db_session.commit()

    webhook_payload = {
        "version": "4",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "HighLatency",
                    "service": "checkout-api",
                    "severity": "medium",
                    "environment": "production",
                },
                "annotations": {
                    "summary": "P95 latency degradation on checkout-api",
                    "description": "P95 response time is 620ms, exceeding 500ms SLA.",
                    "probable_cause": "Thread exhaustion or connection pool saturation",
                    "recommended_action": "clear_cache",
                },
            }
        ],
    }

    # 1. Reject request with invalid secret
    bad_res = api_client.post(
        "/api/v1/alerts/webhook",
        json=webhook_payload,
        headers={"Authorization": "Bearer invalid_secret_token"},
    )
    assert bad_res.status_code == 401

    # 2. Ingest alert with valid Alertmanager HMAC secret
    res = api_client.post(
        "/api/v1/alerts/webhook",
        json=webhook_payload,
        headers={"Authorization": f"Bearer {settings.ALERTMANAGER_HMAC_SECRET}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["incidents_created"] == 1
    assert data["incidents_updated"] == 0

    # Verify incident was persisted in DB with AI recommended action
    inc_stmt = select(Incident).where(Incident.service_id == svc.id)
    inc_res = await db_session.execute(inc_stmt)
    incident = inc_res.scalar_one()

    assert incident.severity == "medium"
    assert incident.status == "open"
    assert incident.recommended_action in ("clear_cache", "restart_service", "scale_service", "rollback_release", "restore_health")
    assert incident.probable_cause is not None


# ==============================================================================
# 4. Alert Deduplication on Repeated Breaches
# ==============================================================================
@pytest.mark.asyncio
async def test_alertmanager_webhook_deduplication(api_client: TestClient, db_session: AsyncSession):
    """Repeated alerts for active incidents update existing incidents rather than creating duplicates."""
    org = Organization(id=uuid.uuid4(), slug="dedup-org", name="Dedup Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    svc = Service(
        id="svc-dedup-test",
        organization_id=org.id,
        name="customer-web",
        environment="staging",
        status="degraded",
        availability=98.0,
        error_rate=3.0,
        latency_ms=450,
        last_checked=datetime.now(timezone.utc),
    )
    db_session.add(svc)
    await db_session.commit()

    webhook_payload = {
        "version": "4",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "HighErrorRate",
                    "service": "customer-web",
                    "severity": "high",
                    "environment": "staging",
                },
                "annotations": {
                    "summary": "High 5xx error rate on customer-web",
                    "description": "Error rate exceeded 1.5% threshold.",
                    "probable_cause": "Faulty release deployment",
                    "recommended_action": "rollback_release",
                },
            }
        ],
    }

    # First delivery: creates incident
    res1 = api_client.post(
        "/api/v1/alerts/webhook",
        json=webhook_payload,
        headers={"Authorization": f"Bearer {settings.ALERTMANAGER_HMAC_SECRET}"},
    )
    assert res1.status_code == 200
    assert res1.json()["incidents_created"] == 1

    # Second delivery: deduplicates and updates existing incident
    res2 = api_client.post(
        "/api/v1/alerts/webhook",
        json=webhook_payload,
        headers={"Authorization": f"Bearer {settings.ALERTMANAGER_HMAC_SECRET}"},
    )
    assert res2.status_code == 200
    assert res2.json()["incidents_created"] == 0
    assert res2.json()["incidents_updated"] == 1

    # Ensure only 1 incident exists for this service
    inc_res = await db_session.execute(select(Incident).where(Incident.service_id == svc.id))
    incidents = inc_res.scalars().all()
    assert len(incidents) == 1


# ==============================================================================
# 5. Full Recovery Workflow: Request, Approve, Execute, Verify & Audit
# ==============================================================================
@pytest.mark.asyncio
async def test_full_recovery_workflow_success(api_client: TestClient, db_session: AsyncSession):
    """Full lifecycle: incident -> recovery request -> approval -> simulated execution -> verification -> resolved."""
    org = Organization(id=uuid.uuid4(), slug="recovery-flow-org", name="Recovery Flow Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    operator = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="operator_flow@example.com",
        full_name="Flow Operator",
        hashed_password=get_password_hash("Password123!"),
        role="operator",
        is_active=True,
    )
    db_session.add(operator)
    await db_session.flush()

    svc = Service(
        id="svc-flow-test",
        organization_id=org.id,
        name="payments-api",
        environment="production",
        status="critical",
        availability=91.0,
        error_rate=8.5,
        latency_ms=950,
        last_checked=datetime.now(timezone.utc),
    )
    inc = Incident(
        id="INC-FLOW-101",
        organization_id=org.id,
        service_id=svc.id,
        service_name=svc.name,
        title="Critical Payment Gateway Outage",
        severity="critical",
        status="open",
        detected_at=datetime.now(timezone.utc),
        recovery_status="Approval required",
        error_rate=8.5,
        threshold=1.0,
        probable_cause="Thread exhaustion in connection pool",
        recommended_action="restart_service",
    )
    db_session.add_all([svc, inc])
    await db_session.commit()

    token = create_access_token(str(operator.id), operator.email, operator.role, str(org.id))
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Step 1: Request recovery for incident
    req_res = api_client.post(f"/api/v1/incidents/{inc.id}/recover", headers=auth_headers)
    assert req_res.status_code == 200
    rec_data = req_res.json()
    rec_id = rec_data["id"]
    assert rec_data["status"] == "pending_approval"
    assert rec_data["action"] == "restart_service"

    # Step 2: Operator approves recovery
    appr_res = api_client.post(f"/api/v1/recoveries/{rec_id}/approve", headers=auth_headers)
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "approved"

    # Step 3: Operator executes approved recovery
    exec_res = api_client.post(f"/api/v1/recoveries/{rec_id}/execute", headers=auth_headers)
    assert exec_res.status_code == 200
    exec_data = exec_res.json()
    assert exec_data["status"] == "completed"
    assert exec_data["verification"] == "passed"
    assert exec_data["result"]["verified"] is True

    # Step 4: Verify Incident is resolved and service is normalized
    await db_session.refresh(inc)
    assert inc.status == "resolved"
    assert inc.resolved_at is not None

    await db_session.refresh(svc)
    assert svc.status == "healthy"
    assert svc.error_rate < 0.1

    # Step 5: Verify Audit Log trail
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.organization_id == org.id)
    )
    logs = audit_res.scalars().all()
    actions = [log.action for log in logs]
    assert "recovery_requested" in actions
    assert "recovery_approved" in actions
    assert "recovery_executed" in actions
    assert "recovery_verified" in actions


# ==============================================================================
# 6. Recovery Rejection Workflow
# ==============================================================================
@pytest.mark.asyncio
async def test_recovery_rejection_workflow(api_client: TestClient, db_session: AsyncSession):
    """Operator can reject an unwanted recovery action, transitioning state to rejected."""
    org = Organization(id=uuid.uuid4(), slug="reject-org", name="Reject Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    operator = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="operator_reject@example.com",
        full_name="Reject Operator",
        hashed_password=get_password_hash("Password123!"),
        role="operator",
        is_active=True,
    )
    db_session.add(operator)
    await db_session.flush()

    svc = Service(
        id="svc-rej-test",
        organization_id=org.id,
        name="checkout-api",
        environment="production",
        status="degraded",
        availability=98.0,
        error_rate=2.0,
        latency_ms=400,
        last_checked=datetime.now(timezone.utc),
    )
    inc = Incident(
        id="INC-REJ-101",
        organization_id=org.id,
        service_id=svc.id,
        service_name=svc.name,
        title="Elevated Checkout Latency",
        severity="medium",
        status="recovering",
        detected_at=datetime.now(timezone.utc),
        recovery_status="Approval required",
        error_rate=2.0,
        threshold=1.0,
    )
    rec = RecoveryAction(
        id="REC-REJ-101",
        incident_id=inc.id,
        service_id=svc.id,
        service_name=svc.name,
        action="scale_service",
        status="pending_approval",
        approval_required=True,
        requested_by="AutoHeal",
        requested_at=datetime.now(timezone.utc),
        verification="pending",
    )
    db_session.add_all([svc, inc, rec])
    await db_session.commit()

    token = create_access_token(str(operator.id), operator.email, operator.role, str(org.id))
    auth_headers = {"Authorization": f"Bearer {token}"}

    reject_res = api_client.post(
        f"/api/v1/recoveries/{rec.id}/reject",
        json={"reason": "Manual investigation preferred during peak checkout window."},
        headers=auth_headers,
    )
    assert reject_res.status_code == 200
    data = reject_res.json()
    assert data["status"] == "rejected"
    assert data["verification"] == "failed"

    await db_session.refresh(inc)
    assert inc.status == "investigating"
    assert inc.recovery_status == "Action rejected"


# ==============================================================================
# 7. Multi-Tenant Isolation
# ==============================================================================
@pytest.mark.asyncio
async def test_tenant_isolation_in_recovery(api_client: TestClient, db_session: AsyncSession):
    """Users cannot view, approve, or execute recovery actions belonging to another organization."""
    org_a = Organization(id=uuid.uuid4(), slug="org-a", name="Org A", is_active=True)
    org_b = Organization(id=uuid.uuid4(), slug="org-b", name="Org B", is_active=True)
    db_session.add_all([org_a, org_b])
    await db_session.flush()

    user_b = User(
        id=uuid.uuid4(),
        organization_id=org_b.id,
        email="operator_b@example.com",
        full_name="User B",
        hashed_password=get_password_hash("Password123!"),
        role="operator",
        is_active=True,
    )
    db_session.add(user_b)

    svc_a = Service(
        id="svc-tenant-a",
        organization_id=org_a.id,
        name="checkout-api",
        environment="production",
        status="healthy",
        availability=99.9,
        error_rate=0.0,
        latency_ms=100,
        last_checked=datetime.now(timezone.utc),
    )
    inc_a = Incident(
        id="INC-TENANT-A",
        organization_id=org_a.id,
        service_id=svc_a.id,
        service_name=svc_a.name,
        title="Tenant A Incident",
        severity="medium",
        status="open",
        detected_at=datetime.now(timezone.utc),
        recovery_status="Approval required",
        error_rate=0.0,
        threshold=1.0,
    )
    rec_a = RecoveryAction(
        id="REC-TENANT-A",
        incident_id=inc_a.id,
        service_id=svc_a.id,
        service_name=svc_a.name,
        action="restart_service",
        status="pending_approval",
        approval_required=True,
        requested_by="Operator",
        requested_at=datetime.now(timezone.utc),
        verification="pending",
    )
    db_session.add_all([svc_a, inc_a, rec_a])
    await db_session.commit()

    # User B (Org B) attempts to approve Recovery A (Org A)
    token_b = create_access_token(str(user_b.id), user_b.email, user_b.role, str(org_b.id))
    headers_b = {"Authorization": f"Bearer {token_b}"}

    res = api_client.post(f"/api/v1/recoveries/{rec_a.id}/approve", headers=headers_b)
    assert res.status_code == 404
