"""
AutoHeal DevOps — Complete End-to-End Workflow Verification
Executes and validates all 17 steps of the full operational self-healing lifecycle:
1. User registers
2. User logs in
3. Authenticated dashboard loads
4. Services are retrieved from the backend
5. Monitoring collects service metrics
6. Alertmanager sends an alert
7. AutoHeal validates the alert
8. An incident is created
9. AI diagnosis runs
10. Recovery recommendation is displayed
11. Authorized operator approves recovery
12. Recovery action executes using safe simulation adapter
13. Post-recovery verification runs
14. Incident status is updated
15. Dashboard reflects the new state
16. Audit events are recorded
17. User downloads an incident report
"""

from datetime import datetime, timezone
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch
import uuid
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.config import get_settings
from app.main import app
from app.models.audit import AuditLog
from app.models.service import Service
from app.models.user import User
from app.services.monitoring import MonitoringService

settings = get_settings()


@pytest.fixture
def e2e_client(db_session: AsyncSession) -> TestClient:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_complete_end_to_end_platform_workflow(
    e2e_client: TestClient, db_session: AsyncSession, seed_data: dict
):
    """
    Executes the complete 17-step self-healing workflow in an integrated runtime environment.
    All state transitions are persisted and asserted directly against the real database.
    """
    client = e2e_client

    # Step 1: User registers
    reg_payload = {
        "email": "lead.operator@autoheal.io",
        "password": "SecurePassword123!",
        "full_name": "Lead SRE Operator",
    }
    reg_res = client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201, f"Registration failed: {reg_res.text}"
    reg_data = reg_res.json()
    assert reg_data["user"]["email"] == "lead.operator@autoheal.io"
    user_id = uuid.UUID(reg_data["user"]["id"])
    user_org_id = uuid.UUID(reg_data["user"]["organization_id"])

    # Upgrade user to operator in organization for recovery approval testing
    user = await db_session.get(User, user_id)
    assert user is not None
    user.role = "operator"

    # Provision unique service in this organization
    service_name = "e2e-order-service"
    service = Service(
        id="svc-e2e-order",
        organization_id=user_org_id,
        name=service_name,
        environment="production",
        status="healthy",
        availability=99.98,
        error_rate=0.12,
        latency_ms=142,
        last_checked=datetime.now(timezone.utc),
    )
    db_session.add(service)
    await db_session.commit()

    # Step 2: User logs in (issues operator access token)
    login_res = client.post(
        "/api/v1/auth/login",
        json={
            "email": "lead.operator@autoheal.io",
            "password": "SecurePassword123!",
        },
    )
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    login_data = login_res.json()
    assert login_data["access_token"] is not None
    auth_headers = {"Authorization": f"Bearer {login_data['access_token']}"}

    # Step 3: Authenticated dashboard profile & settings load
    me_res = client.get("/api/v1/auth/me", headers=auth_headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "lead.operator@autoheal.io"
    assert me_res.json()["role"] == "operator"

    settings_res = client.get("/api/v1/settings", headers=auth_headers)
    assert settings_res.status_code == 200
    assert settings_res.json()["organization"]["id"] == str(user_org_id)

    # Step 4: Monitored services are retrieved
    services_res = client.get("/api/v1/services", headers=auth_headers)
    assert services_res.status_code == 200
    services = services_res.json()
    assert len(services) >= 1
    target_service = services[0]
    service_id = target_service["id"]
    assert target_service["name"] == service_name

    # Step 5: Monitoring collector runs and persists service metrics
    monitoring_svc = MonitoringService()
    mock_resp = httpx.Response(200, json={"status": "ok"})
    with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        metrics = await monitoring_svc.run_monitoring_cycle(db_session)
    assert len(metrics) >= 1

    svc_metrics_res = client.get(
        f"/api/v1/services/{service_id}/metrics", headers=auth_headers
    )
    assert svc_metrics_res.status_code == 200
    metrics_data = svc_metrics_res.json()
    assert metrics_data["serviceId"] == service_id

    # Step 6: Alertmanager prepares an alert payload
    alert_payload = {
        "receiver": "autoheal-webhook",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "HighLatencyDetected",
                    "severity": "critical",
                    "service": service_name,
                },
                "annotations": {
                    "summary": f"High response latency observed on {service_name}",
                    "description": f"95th percentile latency exceeded 800ms for {service_name}",
                    "probable_cause": "Database connection pool exhaustion and memory pressure",
                },
                "startsAt": "2026-11-16T12:00:00Z",
            }
        ],
        "commonLabels": {
            "alertname": "HighLatencyDetected",
            "service": service_name,
        },
        "commonAnnotations": {},
    }
    body_bytes = json.dumps(alert_payload).encode("utf-8")
    secret = settings.ALERTMANAGER_HMAC_SECRET.encode("utf-8")
    signature = hmac.new(secret, body_bytes, hashlib.sha256).hexdigest()

    # Step 7: AutoHeal receives and validates the webhook alert
    webhook_headers = {
        "Content-Type": "application/json",
        "X-AutoHeal-Signature": f"sha256={signature}",
    }
    webhook_res = client.post(
        "/api/v1/alerts/webhook",
        headers=webhook_headers,
        content=body_bytes,
    )
    assert webhook_res.status_code == 200, f"Webhook failed: {webhook_res.text}"
    webhook_data = webhook_res.json()
    assert webhook_data["incidents_created"] >= 1

    # Step 8: An incident is retrieved via the incidents API
    incidents_res = client.get("/api/v1/incidents", headers=auth_headers)
    assert incidents_res.status_code == 200
    incidents = incidents_res.json()
    active_incident = next((i for i in incidents if i["serviceName"] == service_name), None)
    assert active_incident is not None, f"No incident created for {service_name}"
    incident_id = active_incident["id"]

    # Step 9: AI diagnosis result is attached to the incident
    inc_detail_res = client.get(
        f"/api/v1/incidents/{incident_id}", headers=auth_headers
    )
    assert inc_detail_res.status_code == 200
    inc_detail = inc_detail_res.json()
    assert inc_detail["probableCause"] is not None
    assert inc_detail["recommendedAction"] is not None
    assert len(inc_detail["evidence"]) >= 1

    # Step 10: Recovery recommendation is displayed & operator submits recovery request
    recover_req_res = client.post(
        f"/api/v1/incidents/{incident_id}/recover", headers=auth_headers
    )
    assert recover_req_res.status_code == 200
    recovery_data = recover_req_res.json()
    recovery_id = recovery_data["id"]
    assert recovery_data["status"] == "pending_approval"
    assert recovery_data["approvalRequired"] is True

    # Step 11: Authorized operator approves recovery
    approve_res = client.post(
        f"/api/v1/recoveries/{recovery_id}/approve", headers=auth_headers
    )
    assert approve_res.status_code == 200
    approved_data = approve_res.json()
    assert approved_data["status"] == "approved"

    # Step 12: Recovery action executes using safe simulation adapter
    exec_res = client.post(
        f"/api/v1/recoveries/{recovery_id}/execute", headers=auth_headers
    )
    assert exec_res.status_code == 200
    executed_data = exec_res.json()
    assert executed_data["status"] == "completed"

    # Step 13: Post-recovery verification runs
    assert executed_data["verification"] == "passed"
    assert executed_data["durationSeconds"] is not None

    # Step 14: Incident status is updated to resolved
    updated_inc_res = client.get(
        f"/api/v1/incidents/{incident_id}", headers=auth_headers
    )
    assert updated_inc_res.status_code == 200
    updated_inc = updated_inc_res.json()
    assert updated_inc["status"] == "resolved"

    # Step 15: Analytics & Dashboard summary reflect the new state
    analytics_res = client.get(
        "/api/v1/analytics/summary", headers=auth_headers
    )
    assert analytics_res.status_code == 200
    analytics_data = analytics_res.json()
    assert analytics_data["incidentCount"] >= 1
    assert analytics_data["recoverySuccessRate"] >= 0

    # Step 16: Audit logs verify full non-repudiation audit trail
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.resource_id.in_([incident_id, recovery_id]))
    )
    audit_entries = audit_res.scalars().all()
    assert len(audit_entries) >= 2, "Expected audit entries for incident and recovery lifecycle"

    # Step 17: User downloads incident post-mortem report (PDF and JSON)
    pdf_res = client.get(
        f"/api/v1/incidents/{incident_id}/report?format=pdf",
        headers=auth_headers,
    )
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF")

    json_res = client.get(
        f"/api/v1/incidents/{incident_id}/report?format=json",
        headers=auth_headers,
    )
    assert json_res.status_code == 200
    assert "application/json" in json_res.headers["content-type"]
    report_json = json_res.json()
    assert report_json["incident_id"] == incident_id
    assert report_json["status"] == "resolved"
