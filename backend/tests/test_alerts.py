"""
AutoHeal DevOps — Alertmanager Webhook Ingestion & Incident Detection Test Suite
Verifies HMAC authentication, payload parsing, alert deduplication,
and resolved alert handling.
"""

from datetime import datetime, timezone
import hashlib
import hmac
import json
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.config import get_settings
from app.main import app
from app.models import Incident, Organization, Service

settings = get_settings()


@pytest.fixture
def alert_client(db_session: AsyncSession) -> TestClient:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_alert_webhook_unauthorized_without_secret(alert_client: TestClient):
    """Webhook rejects unauthenticated payloads with 401 Unauthorized."""
    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "TestAlert", "service": "checkout-api"},
            }
        ],
    }
    res = alert_client.post("/api/v1/alerts/webhook", json=payload)
    assert res.status_code == 401
    assert "Unauthorized" in res.json()["detail"]


@pytest.mark.asyncio
async def test_alert_webhook_authorized_via_secret_header(alert_client: TestClient, db_session: AsyncSession):
    """Webhook accepts payloads authenticated with X-Alertmanager-Secret header."""
    org = Organization(id=uuid.uuid4(), slug="alert-org-1", name="Alert Org 1", is_active=True)
    db_session.add(org)
    await db_session.flush()

    svc = Service(
        id="svc-checkout-alert",
        organization_id=org.id,
        name="checkout-api",
        environment="production",
        status="healthy",
        availability=99.9,
        error_rate=0.01,
        latency_ms=100,
        last_checked=datetime.now(timezone.utc),
    )
    db_session.add(svc)
    await db_session.commit()

    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "HighErrorRate",
                    "service": "checkout-api",
                    "severity": "critical",
                },
                "annotations": {
                    "summary": "High 5xx error rate on checkout-api",
                    "description": "Observed error rate exceeded 2.5%",
                },
            }
        ],
    }

    res = alert_client.post(
        "/api/v1/alerts/webhook",
        json=payload,
        headers={"X-Alertmanager-Secret": settings.ALERTMANAGER_HMAC_SECRET},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["incidents_created"] == 1

    # Verify incident created in DB
    inc_stmt = select(Incident).where(Incident.service_id == svc.id)
    inc_res = await db_session.execute(inc_stmt)
    incident = inc_res.scalar_one()
    assert incident.severity == "critical"
    assert incident.status == "open"
    assert incident.probable_cause is not None


@pytest.mark.asyncio
async def test_alert_webhook_authorized_via_hmac_signature(alert_client: TestClient, db_session: AsyncSession):
    """Webhook accepts payloads authenticated via HMAC-SHA256 signature header."""
    org = Organization(id=uuid.uuid4(), slug="alert-org-hmac", name="Alert Org HMAC", is_active=True)
    db_session.add(org)
    await db_session.flush()

    svc = Service(
        id="svc-payments-hmac",
        organization_id=org.id,
        name="payments-api",
        environment="production",
        status="healthy",
        availability=99.9,
        error_rate=0.01,
        latency_ms=100,
        last_checked=datetime.now(timezone.utc),
    )
    db_session.add(svc)
    await db_session.commit()

    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "CPUSaturation",
                    "service": "payments-api",
                    "severity": "warning",
                },
                "annotations": {
                    "summary": "CPU utilization sustained >85%",
                },
            }
        ],
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(settings.ALERTMANAGER_HMAC_SECRET.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

    res = alert_client.post(
        "/api/v1/alerts/webhook",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-AutoHeal-Signature": f"sha256={sig}",
        },
    )
    assert res.status_code == 200
    assert res.json()["incidents_created"] == 1


@pytest.mark.asyncio
async def test_alert_deduplication_for_existing_open_incident(alert_client: TestClient, db_session: AsyncSession):
    """Repeated alerts for the same service do not create duplicate open incidents."""
    org = Organization(id=uuid.uuid4(), slug="dedup-org", name="Dedup Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    svc = Service(
        id="svc-dedup",
        organization_id=org.id,
        name="checkout-api",
        environment="production",
        status="degraded",
        availability=98.0,
        error_rate=1.8,
        latency_ms=350,
        last_checked=datetime.now(timezone.utc),
    )
    db_session.add(svc)
    await db_session.commit()

    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "HighLatency", "service": "checkout-api", "severity": "medium"},
                "annotations": {"summary": "High latency detected"},
            }
        ],
    }

    # 1. First alert creates incident
    res1 = alert_client.post(
        "/api/v1/alerts/webhook",
        json=payload,
        headers={"X-Alertmanager-Secret": settings.ALERTMANAGER_HMAC_SECRET},
    )
    assert res1.status_code == 200
    assert res1.json()["incidents_created"] == 1

    # 2. Second alert updates existing incident without creating a duplicate
    res2 = alert_client.post(
        "/api/v1/alerts/webhook",
        json=payload,
        headers={"X-Alertmanager-Secret": settings.ALERTMANAGER_HMAC_SECRET},
    )
    assert res2.status_code == 200
    assert res2.json()["incidents_created"] == 0
    assert res2.json()["incidents_updated"] == 1

    # Verify only 1 incident exists in database
    inc_stmt = select(Incident).where(Incident.service_id == svc.id)
    inc_res = await db_session.execute(inc_stmt)
    incidents = inc_res.scalars().all()
    assert len(incidents) == 1


@pytest.mark.asyncio
async def test_alert_resolved_state_transitions_incident(alert_client: TestClient, db_session: AsyncSession):
    """Alertmanager 'resolved' alert transitions active incident to resolved."""
    org = Organization(id=uuid.uuid4(), slug="resolved-org", name="Resolved Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    svc = Service(
        id="svc-resolved-test",
        organization_id=org.id,
        name="payments-api",
        environment="production",
        status="degraded",
        availability=98.5,
        error_rate=1.2,
        latency_ms=250,
        last_checked=datetime.now(timezone.utc),
    )
    db_session.add(svc)
    await db_session.flush()

    # Pre-existing active incident
    incident = Incident(
        id="INC-PRE-01",
        organization_id=org.id,
        service_id=svc.id,
        service_name=svc.name,
        title="High error rate on payments-api",
        severity="high",
        status="open",
        detected_at=datetime.now(timezone.utc),
        recovery_status="Approval required",
        error_rate=1.2,
        threshold=1.0,
    )
    db_session.add(incident)
    await db_session.commit()

    # Send resolved alert
    payload = {
        "status": "resolved",
        "alerts": [
            {
                "status": "resolved",
                "labels": {"alertname": "HighErrorRate", "service": "payments-api"},
            }
        ],
    }

    res = alert_client.post(
        "/api/v1/alerts/webhook",
        json=payload,
        headers={"X-Alertmanager-Secret": settings.ALERTMANAGER_HMAC_SECRET},
    )
    assert res.status_code == 200
    assert res.json()["incidents_updated"] == 1

    await db_session.refresh(incident)
    assert incident.status == "resolved"
    assert incident.resolved_at is not None


@pytest.mark.asyncio
async def test_duplicate_resolved_alert_does_not_reopen_or_duplicate_incident(alert_client: TestClient, db_session: AsyncSession):
    """Subsequent duplicate 'resolved' alerts do not reopen or duplicate resolved incidents."""
    org = Organization(id=uuid.uuid4(), slug="dup-resolved-org", name="Dup Resolved Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    svc = Service(
        id="svc-dup-resolved",
        organization_id=org.id,
        name="checkout-api",
        environment="production",
        status="healthy",
        availability=99.9,
        error_rate=0.0,
        latency_ms=25,
        last_checked=datetime.now(timezone.utc),
    )
    db_session.add(svc)
    await db_session.flush()

    # Pre-existing resolved incident
    incident = Incident(
        id="INC-ALREADY-RESOLVED",
        organization_id=org.id,
        service_id=svc.id,
        service_name=svc.name,
        title="High error rate on checkout-api",
        severity="high",
        status="resolved",
        detected_at=datetime.now(timezone.utc),
        resolved_at=datetime.now(timezone.utc),
        recovery_status="Resolved by Alertmanager",
        error_rate=0.0,
        threshold=1.0,
    )
    db_session.add(incident)
    await db_session.commit()

    # Send duplicate resolved alert
    payload = {
        "status": "resolved",
        "alerts": [
            {
                "status": "resolved",
                "labels": {"alertname": "HighErrorRate", "service": "checkout-api"},
            }
        ],
    }

    res = alert_client.post(
        "/api/v1/alerts/webhook",
        json=payload,
        headers={"X-Alertmanager-Secret": settings.ALERTMANAGER_HMAC_SECRET},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["incidents_created"] == 0
    assert data["incidents_updated"] == 0
    assert "no active incident existed" in data["details"][0]

    # Verify incident remains resolved in DB and no new incident was created
    await db_session.refresh(incident)
    assert incident.status == "resolved"

    all_incs = (await db_session.execute(select(Incident).where(Incident.service_id == svc.id))).scalars().all()
    assert len(all_incs) == 1

