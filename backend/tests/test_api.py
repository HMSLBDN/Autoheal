"""
AutoHeal DevOps — Comprehensive API & Integration Test Suite
"""

from fastapi.testclient import TestClient
from app.api.deps import get_current_org, get_db
from app.main import app


def test_health_endpoint():
    """Public health probe must return 200 OK without requiring authentication."""
    with TestClient(app) as unauth_client:
        res = unauth_client.get("/api/v1/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "environment" in data


def test_root_endpoint():
    """Root metadata discovery endpoint."""
    with TestClient(app) as unauth_client:
        res = unauth_client.get("/")
        assert res.status_code == 200
        assert res.json()["service"] == "AutoHeal DevOps API"


def test_security_fail_closed_without_auth():
    """Protected data endpoints must fail closed (401 Unauthorized) when unauthenticated."""
    with TestClient(app) as unauth_client:
        res = unauth_client.get("/api/v1/services")
        assert res.status_code == 401
        assert "Authentication required" in res.json()["detail"]

        res_inc = unauth_client.get("/api/v1/incidents")
        assert res_inc.status_code == 401


def test_services_list_and_filter(client: TestClient):
    """Services listing returns org-isolated services matching frontend contract."""
    res = client.get("/api/v1/services")
    assert res.status_code == 200
    services = res.json()
    assert len(services) == 2
    # Verify exact frontend camelCase field names
    first = services[0]
    assert "errorRate" in first
    assert "latencyMs" in first
    assert "lastChecked" in first
    assert first["status"] in ["healthy", "degraded", "critical"]

    # Filter by environment
    res_prod = client.get("/api/v1/services?environment=production")
    assert res_prod.status_code == 200
    assert len(res_prod.json()) == 1
    assert res_prod.json()[0]["name"] == "checkout-api"


def test_service_detail_and_metrics(client: TestClient):
    """Service detail and telemetry metrics endpoints."""
    res = client.get("/api/v1/services/svc-checkout")
    assert res.status_code == 200
    assert res.json()["name"] == "checkout-api"

    res_metrics = client.get("/api/v1/services/svc-checkout/metrics")
    assert res_metrics.status_code == 200
    metrics = res_metrics.json()
    assert metrics["serviceId"] == "svc-checkout"
    assert "cpuPercent" in metrics
    assert "memoryPercent" in metrics
    assert isinstance(metrics["history"], list)
    assert len(metrics["history"]) > 0

    # Missing service returns 404
    res_404 = client.get("/api/v1/services/non-existent-svc")
    assert res_404.status_code == 404


def test_incidents_list_and_details(client: TestClient):
    """Incidents listing and deep detail with evidence & event series."""
    res = client.get("/api/v1/incidents")
    assert res.status_code == 200
    incidents = res.json()
    assert len(incidents) == 2

    # Detail query
    res_detail = client.get("/api/v1/incidents/INC-1001")
    assert res_detail.status_code == 200
    inc = res_detail.json()
    assert inc["id"] == "INC-1001"
    assert inc["serviceName"] == "customer-web"
    assert inc["severity"] == "high"
    assert len(inc["evidence"]) == 1
    assert inc["evidence"][0]["kind"] == "metric"
    assert len(inc["events"]) == 1
    assert inc["events"][0]["tone"] == "warning"

    # Missing incident returns 404
    res_404 = client.get("/api/v1/incidents/INC-999999")
    assert res_404.status_code == 404


def test_recovery_approval_flow(client: TestClient):
    """Recovery approval transitions status to approved and prevents duplicate approval."""
    # 1. Approve pending recovery
    res = client.post("/api/v1/recoveries/REC-101/approve")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "approved"
    assert data["id"] == "REC-101"

    # 2. State transition guard: duplicate approval triggers 409 Conflict
    res_duplicate = client.post("/api/v1/recoveries/REC-101/approve")
    assert res_duplicate.status_code == 409
    assert "cannot be approved" in res_duplicate.json()["detail"]


def test_recovery_rejection_flow(client: TestClient):
    """Recovery rejection sets status strictly to 'rejected' (not 'failed') with audit reason."""
    res = client.post(
        "/api/v1/recoveries/REC-101/reject",
        json={"reason": "Deployment window closed by change board"},
    )
    assert res.status_code == 200
    data = res.json()
    # Crucial assertion: status must be 'rejected', NOT 'failed'
    assert data["status"] == "rejected"
    assert data["verification"] == "failed"
    assert "Deployment window closed" in data["result"]["summary"]

    # Duplicate rejection triggers 409 Conflict
    res_duplicate = client.post("/api/v1/recoveries/REC-101/reject")
    assert res_duplicate.status_code == 409


def test_incident_recovery_request(client: TestClient):
    """Requesting recovery creates a new pending recovery action and updates incident status."""
    res = client.post("/api/v1/incidents/INC-1001/recover")
    # REC-101 already active for INC-1001 in fixture, so should return 409 Conflict!
    assert res.status_code == 409
    assert "already active" in res.json()["detail"]

    # Request recovery on resolved incident triggers 409
    res_resolved = client.post("/api/v1/incidents/INC-1002/recover")
    assert res_resolved.status_code == 409
    assert "already resolved" in res_resolved.json()["detail"]


def test_pdf_report_download(client: TestClient):
    """Incident report endpoint returns real binary downloadable PDF."""
    res = client.get("/api/v1/incidents/INC-1001/report")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert 'attachment; filename="INC-1001-report.pdf"' in res.headers["content-disposition"]
    # Verify PDF magic bytes '%PDF-'
    assert res.content.startswith(b"%PDF-")
    assert len(res.content) > 1000  # Substantial binary PDF


def test_analytics_summary(client: TestClient):
    """Analytics summary endpoint returns MTTR, availability, and 7-day history."""
    res = client.get("/api/v1/analytics/summary")
    assert res.status_code == 200
    data = res.json()
    assert "detectionLatencySeconds" in data
    assert "recoveryDurationMinutes" in data
    assert "recoverySuccessRate" in data
    assert "availability" in data
    assert data["incidentCount"] == 2
    assert len(data["history"]) == 7


def test_organization_multi_tenant_isolation(client: TestClient, seed_data: dict):
    """
    Strict multi-tenancy verification:
    Organization Alpha must NEVER access or modify Organization Beta's data, and vice versa.
    """
    org_a = seed_data["org_a"]
    org_b = seed_data["org_b"]

    # 1. Org A sees its 2 services, does NOT see Org B's payments-api
    res_a = client.get("/api/v1/services")
    names_a = [s["name"] for s in res_a.json()]
    assert "checkout-api" in names_a
    assert "payments-api" not in names_a

    # 2. Org A querying Org B's incident ID returns 404
    res_cross_incident = client.get("/api/v1/incidents/INC-9999")
    assert res_cross_incident.status_code == 404

    # 3. Org A attempting to download Org B's incident report returns 404
    res_cross_report = client.get("/api/v1/incidents/INC-9999/report")
    assert res_cross_report.status_code == 404

    # 4. Switch context to Org B
    app.dependency_overrides[get_current_org] = lambda: org_b

    # Org B sees only its payments-api, does NOT see Org A's checkout-api
    res_b = client.get("/api/v1/services")
    names_b = [s["name"] for s in res_b.json()]
    assert "payments-api" in names_b
    assert "checkout-api" not in names_b

    # Org B querying Org A's incident returns 404
    res_b_cross = client.get("/api/v1/incidents/INC-1001")
    assert res_b_cross.status_code == 404

    # Reset back to Org A
    app.dependency_overrides[get_current_org] = lambda: org_a
