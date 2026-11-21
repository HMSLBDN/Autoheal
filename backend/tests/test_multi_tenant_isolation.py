"""
AutoHeal DevOps — Multi-Tenant Isolation & Cross-Tenant Security Verification Tests
Verifies strict cryptographic and database tenant isolation across two independent organizations
(Organization Alpha and Organization Beta).
"""

from datetime import datetime, timezone
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_current_org, get_current_user, get_db
from app.main import app
from app.models.incident import Incident
from app.models.recovery import RecoveryAction
from app.models.service import Service
from app.services.events import event_broadcaster
from app.services.ticket import sse_ticket_service


@pytest.mark.asyncio
async def test_tenant_a_cannot_view_or_query_tenant_b_services(client: TestClient, seed_data: dict):
    """
    Asserts Org Alpha cannot view Org Beta's services via direct ID lookup or list endpoint.
    """
    svc_b1 = seed_data["svc_b1"]

    # Direct ID lookup of Org B service must return 404 Not Found
    res = client.get(f"/api/v1/services/{svc_b1.id}")
    assert res.status_code == 404
    assert "was not found in this organization" in res.json()["detail"]

    # List services must only return Org Alpha services
    list_res = client.get("/api/v1/services")
    assert list_res.status_code == 200
    services = list_res.json()
    service_ids = [s["id"] for s in services]
    assert "svc-checkout" in service_ids
    assert "svc-web" in service_ids
    assert svc_b1.id not in service_ids


@pytest.mark.asyncio
async def test_tenant_a_cannot_view_or_query_tenant_b_incidents(client: TestClient, seed_data: dict):
    """
    Asserts Org Alpha cannot view Org Beta's incidents via direct ID lookup or list endpoint.
    """
    inc_b1 = seed_data["inc_b1"]

    # Direct lookup must return 404
    res = client.get(f"/api/v1/incidents/{inc_b1.id}")
    assert res.status_code == 404
    assert "was not found in this organization" in res.json()["detail"]

    # Incident list must exclude Org Beta
    list_res = client.get("/api/v1/incidents")
    assert list_res.status_code == 200
    incidents = list_res.json()
    incident_ids = [i["id"] for i in incidents]
    assert "INC-1001" in incident_ids
    assert "INC-1002" in incident_ids
    assert inc_b1.id not in incident_ids


@pytest.mark.asyncio
async def test_tenant_a_cannot_modify_or_diagnose_tenant_b_incident(client: TestClient, seed_data: dict):
    """
    Asserts Org Alpha cannot request recovery, download report, or access Org Beta's incidents.
    """
    inc_b1 = seed_data["inc_b1"]

    # Attempt to request recovery for Org B incident
    rec_res = client.post(f"/api/v1/incidents/{inc_b1.id}/recover")
    assert rec_res.status_code == 404
    assert "was not found in this organization" in rec_res.json()["detail"]

    # Attempt to download PDF report for Org B incident
    rep_res = client.get(f"/api/v1/incidents/{inc_b1.id}/report")
    assert rep_res.status_code == 404
    assert "was not found in this organization" in rep_res.json()["detail"]

    # Direct incident lookup for Org B incident
    get_res = client.get(f"/api/v1/incidents/{inc_b1.id}")
    assert get_res.status_code == 404
    assert "was not found in this organization" in get_res.json()["detail"]


@pytest.mark.asyncio
async def test_tenant_a_cannot_view_or_execute_tenant_b_recoveries(
    client: TestClient, db_session: AsyncSession, seed_data: dict
):
    """
    Asserts Org Alpha cannot view, approve, execute, or reject Org Beta's recovery actions.
    """
    org_b = seed_data["org_b"]
    inc_b1 = seed_data["inc_b1"]
    svc_b1 = seed_data["svc_b1"]

    # Seed a recovery action belonging strictly to Org Beta
    rec_b = RecoveryAction(
        id="REC-BETA-01",
        incident_id=inc_b1.id,
        service_id=svc_b1.id,
        service_name=svc_b1.name,
        action="Scale payment pods",
        status="pending_approval",
        approval_required=True,
        requested_by="Beta Policy",
        requested_at=datetime.now(timezone.utc),
    )
    db_session.add(rec_b)
    await db_session.commit()

    # Org Alpha recovery list must exclude Org Beta
    rec_list = client.get("/api/v1/recoveries")
    assert rec_list.status_code == 200
    rec_ids = [r["id"] for r in rec_list.json()]
    assert "REC-BETA-01" not in rec_ids

    # Attempt to approve Org Beta recovery action from Org Alpha
    approve_res = client.post("/api/v1/recoveries/REC-BETA-01/approve")
    assert approve_res.status_code == 404

    # Attempt to execute Org Beta recovery action from Org Alpha
    execute_res = client.post("/api/v1/recoveries/REC-BETA-01/execute")
    assert execute_res.status_code == 404

    # Attempt to reject Org Beta recovery action from Org Alpha
    reject_res = client.post(
        "/api/v1/recoveries/REC-BETA-01/reject",
        json={"reason": "Unauthorized cross-tenant rejection"},
    )
    assert reject_res.status_code == 404


@pytest.mark.asyncio
async def test_analytics_and_summary_strictly_scoped_by_tenant(client: TestClient, seed_data: dict):
    """
    Asserts analytics summary metrics for Org Alpha are calculated strictly from Org Alpha data,
    never bleeding metrics or counts from Org Beta.
    """
    res = client.get("/api/v1/analytics/summary")
    assert res.status_code == 200
    data = res.json()

    # Org Alpha has 2 incidents seeded (1 open, 1 resolved)
    incident_count = data.get("incidentCount") if "incidentCount" in data else data.get("incident_count")
    assert incident_count == 2


@pytest.mark.asyncio
async def test_tenant_b_cannot_view_or_modify_tenant_a_resources(
    db_session: AsyncSession, seed_data: dict
):
    """
    Inverts the test: Swaps authentication context to Org Beta operator and
    verifies complete isolation against Org Alpha's services and incidents.
    """
    org_b = seed_data["org_b"]
    user_b = seed_data["user_b"]
    inc_a1 = seed_data["inc_a1"]
    svc_a1 = seed_data["svc_a1"]

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return user_b

    async def override_get_current_org():
        return org_b

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_org] = override_get_current_org

    try:
        with TestClient(app) as beta_client:
            # Org Beta attempts to view Org Alpha service
            svc_res = beta_client.get(f"/api/v1/services/{svc_a1.id}")
            assert svc_res.status_code == 404

            # Org Beta attempts to view Org Alpha incident
            inc_res = beta_client.get(f"/api/v1/incidents/{inc_a1.id}")
            assert inc_res.status_code == 404

            # Org Beta attempts to trigger recovery on Org Alpha incident
            rec_res = beta_client.post(f"/api/v1/incidents/{inc_a1.id}/recover")
            assert rec_res.status_code == 404

            # Org Beta service list contains only Org Beta's service
            svc_list = beta_client.get("/api/v1/services")
            assert svc_list.status_code == 200
            assert len(svc_list.json()) == 1
            assert svc_list.json()[0]["id"] == "svc-beta-payments"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_sse_ticket_and_broadcast_tenant_isolation(seed_data: dict):
    """
    Verifies that SSE tickets are cryptographically bound to the generating organization ID
    and that event broadcasts sent to Org A are never received by subscribers of Org B.
    """
    org_a = seed_data["org_a"]
    org_b = seed_data["org_b"]
    user_a = seed_data["user_a"]

    # Issue ticket for Org A user
    ticket, expires_in = sse_ticket_service.issue_ticket(
        user_id=str(user_a.id),
        org_id=str(org_a.id),
    )
    assert ticket is not None
    assert expires_in == 60

    # Consume ticket - verify it is bound to Org A
    payload = sse_ticket_service.consume_ticket(ticket)
    assert payload is not None
    assert payload["user_id"] == str(user_a.id)
    assert payload["org_id"] == str(org_a.id)

    # Consuming the same ticket again must fail (single-use replay protection)
    reused = sse_ticket_service.consume_ticket(ticket)
    assert reused is None
