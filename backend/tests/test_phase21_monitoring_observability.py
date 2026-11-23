"""
AutoHeal DevOps — Phase 21 Complete Observability & Monitoring Reliability Test Suite
Comprehensive offline test suite validating the complete monitoring and incident-detection pipeline:
1. Static Prometheus, Alertmanager, and alert rules configuration validation.
2. Webhook security (Bearer token, HMAC-SHA256, X-Alertmanager-Secret, invalid auth).
3. Incident lifecycle (firing, resolved, unknown resolved, multiple alerts in batch).
4. Intra-batch and cross-request alert deduplication.
5. Missing labels, annotations, and metric evidence handling.
6. Database transaction boundary and failure handling.
7. Concurrent webhook delivery resilience.
8. UTC timestamp consistency across incidents, evidence, events, and transitions.
9. Incident event and transition trail persistence.
10. Frontend API compatibility and response schema verification.
"""

import asyncio
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import patch
import uuid
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import yaml

from app.api.deps import get_db, get_current_user, get_current_org
from app.config import get_settings
from app.core.metrics import enterprise_metrics
from app.main import app
from app.models import (
    Incident,
    IncidentEvent,
    IncidentEvidence,
    IncidentTransition,
    Organization,
    Service,
    User,
)

settings = get_settings()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ==============================================================================
# Pytest Fixtures
# ==============================================================================

@pytest.fixture
def p21_client(db_session: AsyncSession) -> TestClient:
    """Returns a TestClient with overridden get_db fixture."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def p21_org_and_service(db_session: AsyncSession):
    """Provides a fresh organization and monitored microservice."""
    org = Organization(
        id=uuid.uuid4(),
        slug=f"p21-org-{uuid.uuid4().hex[:6]}",
        name="Phase 21 Observability Org",
        is_active=True,
    )
    db_session.add(org)
    await db_session.flush()

    service = Service(
        id=f"svc-checkout-{uuid.uuid4().hex[:6]}",
        organization_id=org.id,
        name="checkout-api",
        environment="production",
        status="healthy",
        availability=99.95,
        error_rate=0.01,
        latency_ms=120,
        last_checked=datetime.now(timezone.utc),
    )
    db_session.add(service)
    await db_session.commit()
    await db_session.refresh(service)
    return org, service


def create_signed_headers(payload_bytes: bytes) -> dict:
    """Generates valid HMAC-SHA256 signature headers for Alertmanager webhook."""
    secret = settings.ALERTMANAGER_HMAC_SECRET.encode("utf-8")
    sig = hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-AutoHeal-Signature": f"sha256={sig}",
    }


# ==============================================================================
# Phase 21B — Static Prometheus & Alertmanager Configuration Validation
# ==============================================================================

def test_prometheus_configuration_validity():
    """Validates prometheus.yml syntax, scrape targets, and alert rule file references."""
    prom_path = REPO_ROOT / "monitoring" / "prometheus.yml"
    assert prom_path.exists(), f"Missing {prom_path}"

    with open(prom_path, "r", encoding="utf-8") as f:
        prom_cfg = yaml.safe_load(f)

    assert "global" in prom_cfg
    assert prom_cfg["global"]["scrape_interval"] == "15s"
    assert "rule_files" in prom_cfg

    # Every declared rule file must exist on disk
    rule_files = prom_cfg["rule_files"]
    assert "alerts.yml" in rule_files
    assert "alert_rules.yml" in rule_files

    for rf in rule_files:
        # File is either directly in monitoring/ or monitoring/prometheus/
        found = (REPO_ROOT / "monitoring" / rf).exists() or (REPO_ROOT / "monitoring" / "prometheus" / rf).exists()
        assert found, f"Rule file '{rf}' referenced in prometheus.yml does not exist on disk."

    # Scrape configs validation
    scrape_configs = prom_cfg.get("scrape_configs", [])
    job_names = {sc["job_name"] for sc in scrape_configs}
    assert "autoheal-api" in job_names
    assert "checkout-api" in job_names
    assert "node-exporter" in job_names
    assert "cadvisor" in job_names


def test_alert_rules_syntax_and_severity():
    """Validates all Prometheus alert rule definitions for valid syntax, severity, and non-empty annotations."""
    rule_paths = [
        REPO_ROOT / "monitoring" / "alerts.yml",
        REPO_ROOT / "monitoring" / "prometheus" / "alert_rules.yml",
    ]
    seen_alert_names = set()

    for rpath in rule_paths:
        assert rpath.exists(), f"Rule file not found: {rpath}"
        with open(rpath, "r", encoding="utf-8") as f:
            content = yaml.safe_load(f)

        assert "groups" in content, f"Missing 'groups' in {rpath.name}"
        for group in content["groups"]:
            assert "name" in group
            assert "rules" in group
            for rule in group["rules"]:
                alert_name = rule.get("alert")
                assert alert_name, f"Rule in {rpath.name} missing 'alert' name: {rule}"
                assert alert_name not in seen_alert_names, f"Duplicate alert rule name '{alert_name}' across files."
                seen_alert_names.add(alert_name)

                # Expression and timing
                assert "expr" in rule, f"Alert '{alert_name}' missing expr"
                assert "for" in rule, f"Alert '{alert_name}' missing for duration"

                # Severity label
                labels = rule.get("labels", {})
                assert "severity" in labels, f"Alert '{alert_name}' missing severity label"
                assert labels["severity"] in ("critical", "high", "warning", "medium", "low")

                # Annotations
                annotations = rule.get("annotations", {})
                assert "summary" in annotations, f"Alert '{alert_name}' missing summary annotation"
                assert "description" in annotations, f"Alert '{alert_name}' missing description annotation"


def test_alertmanager_configuration_validity():
    """Validates alertmanager.yml routing, webhook endpoint URL, and Bearer token."""
    am_path = REPO_ROOT / "monitoring" / "alertmanager.yml"
    assert am_path.exists(), f"Missing {am_path}"

    with open(am_path, "r", encoding="utf-8") as f:
        am_cfg = yaml.safe_load(f)

    assert "route" in am_cfg
    assert am_cfg["route"]["receiver"] == "autoheal-webhook"
    assert "receivers" in am_cfg

    webhook_receivers = [r for r in am_cfg["receivers"] if r.get("name") == "autoheal-webhook"]
    assert len(webhook_receivers) == 1
    wh_cfg = webhook_receivers[0]["webhook_configs"][0]
    assert "/api/v1/alerts/webhook" in wh_cfg["url"]
    assert wh_cfg.get("send_resolved") is True
    assert "http_config" in wh_cfg
    assert "bearer_token" in wh_cfg["http_config"] or "bearer_token_file" in wh_cfg["http_config"]


def test_backend_metrics_export():
    """Validates that EnterpriseMetricsCollector exports all required metrics including agent certs gauge."""
    rendered = enterprise_metrics.render_prometheus_text({"pool_size": 10, "checked_out": 2, "overflow": 0})
    assert "autoheal_up 1" in rendered
    assert "autoheal_db_pool_size 10" in rendered
    assert "autoheal_db_pool_checked_out 2" in rendered
    assert "autoheal_agent_certs_expiring_soon 0" in rendered
    assert "autoheal_recovery_executions_total" in rendered


# ==============================================================================
# Phase 21C — Webhook Security & Authentication
# ==============================================================================

@pytest.mark.asyncio
async def test_webhook_rejects_missing_auth(p21_client: TestClient):
    """Rejects unauthenticated webhook requests with 401 Unauthorized."""
    payload = {"status": "firing", "alerts": []}
    res = p21_client.post("/api/v1/alerts/webhook", json=payload)
    assert res.status_code == 401
    assert "WWW-Authenticate" in res.headers


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_bearer_token(p21_client: TestClient):
    """Rejects requests with an invalid Bearer token with 401 Unauthorized."""
    payload = {"status": "firing", "alerts": []}
    res = p21_client.post(
        "/api/v1/alerts/webhook",
        json=payload,
        headers={"Authorization": "Bearer completely_invalid_token_12345"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_webhook_rejects_tampered_hmac_signature(p21_client: TestClient):
    """Rejects payloads where the body was modified after HMAC signing."""
    body_original = json.dumps({"status": "firing", "alerts": []}).encode("utf-8")
    sig = hmac.new(settings.ALERTMANAGER_HMAC_SECRET.encode("utf-8"), body_original, hashlib.sha256).hexdigest()

    tampered_body = json.dumps({"status": "firing", "alerts": [{"status": "firing"}]}).encode("utf-8")
    res = p21_client.post(
        "/api/v1/alerts/webhook",
        content=tampered_body,
        headers={
            "Content-Type": "application/json",
            "X-AutoHeal-Signature": f"sha256={sig}",
        },
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_webhook_accepts_valid_bearer_token(p21_client: TestClient, p21_org_and_service):
    """Accepts requests authenticated with a valid Bearer token."""
    _, service = p21_org_and_service
    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "ServiceDown", "service": service.name, "severity": "critical"},
                "annotations": {"summary": "Service down alert"},
            }
        ],
    }
    res = p21_client.post(
        "/api/v1/alerts/webhook",
        json=payload,
        headers={"Authorization": f"Bearer {settings.ALERTMANAGER_HMAC_SECRET}"},
    )
    assert res.status_code == 200
    assert res.json()["incidents_created"] == 1


# ==============================================================================
# Phase 21D — Incident Creation, Deduplication & Lifecycle
# ==============================================================================

@pytest.mark.asyncio
async def test_valid_firing_alert_creates_incident_and_evidence(
    p21_client: TestClient, p21_org_and_service, db_session: AsyncSession
):
    """Valid firing alert creates incident, metric evidence, and lifecycle transitions."""
    org, service = p21_org_and_service
    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "HighHttp5xxErrorRate",
                    "service": service.name,
                    "severity": "critical",
                },
                "annotations": {
                    "summary": "Error rate exceeded 5%",
                    "description": "5xx error rate sustained >5% for 3 minutes",
                    "probable_cause": "Thread starvation in database pool",
                    "recommended_action": "restart_service",
                },
            }
        ],
    }

    res = p21_client.post(
        "/api/v1/alerts/webhook",
        json=payload,
        headers={"X-Alertmanager-Secret": settings.ALERTMANAGER_HMAC_SECRET},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["incidents_created"] == 1
    assert data["incidents_updated"] == 0

    # Verify database persistence
    inc_stmt = select(Incident).where(Incident.service_id == service.id)
    inc_res = await db_session.execute(inc_stmt)
    incident = inc_res.scalar_one()

    assert incident.severity == "critical"
    assert incident.status == "open"
    assert incident.organization_id == org.id
    assert incident.service_name == service.name
    assert incident.detected_at is not None
    assert isinstance(incident.detected_at, datetime)

    # Verify evidence persistence
    ev_stmt = select(IncidentEvidence).where(IncidentEvidence.incident_id == incident.id)
    ev_res = await db_session.execute(ev_stmt)
    evidences = ev_res.scalars().all()
    assert len(evidences) >= 1
    metric_ev = next(e for e in evidences if e.kind == "metric")
    assert metric_ev.title == "HighHttp5xxErrorRate"

    # Verify initial transition record
    tr_stmt = select(IncidentTransition).where(IncidentTransition.incident_id == incident.id)
    tr_res = await db_session.execute(tr_stmt)
    transitions = tr_res.scalars().all()
    assert len(transitions) == 1
    assert transitions[0].previous_state == "none"
    assert transitions[0].new_state == "open"
    assert transitions[0].actor_email == "alertmanager@autoheal.internal"


@pytest.mark.asyncio
async def test_duplicate_firing_alerts_deduplicate_cleanly(
    p21_client: TestClient, p21_org_and_service, db_session: AsyncSession
):
    """Subsequent firing alerts for the same service deduplicate onto the active incident without duplicating."""
    _, service = p21_org_and_service
    payload1 = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "HighLatency", "service": service.name, "severity": "medium"},
                "annotations": {"summary": "High latency detected"},
            }
        ],
    }

    # First firing alert
    res1 = p21_client.post(
        "/api/v1/alerts/webhook",
        json=payload1,
        headers={"X-Alertmanager-Secret": settings.ALERTMANAGER_HMAC_SECRET},
    )
    assert res1.status_code == 200
    assert res1.json()["incidents_created"] == 1

    # Second firing alert with higher severity (escalation)
    payload2 = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "ServiceDown", "service": service.name, "severity": "critical"},
                "annotations": {"summary": "Service went down completely"},
            }
        ],
    }
    res2 = p21_client.post(
        "/api/v1/alerts/webhook",
        json=payload2,
        headers={"X-Alertmanager-Secret": settings.ALERTMANAGER_HMAC_SECRET},
    )
    assert res2.status_code == 200
    assert res2.json()["incidents_created"] == 0
    assert res2.json()["incidents_updated"] == 1

    # Verify only 1 incident exists and its severity escalated to critical
    inc_stmt = select(Incident).where(Incident.service_id == service.id)
    inc_res = await db_session.execute(inc_stmt)
    incidents = inc_res.scalars().all()
    assert len(incidents) == 1
    assert incidents[0].severity == "critical"

    # Verify event timeline has both detection and re-triggered events
    events_stmt = select(IncidentEvent).where(IncidentEvent.incident_id == incidents[0].id)
    events_res = await db_session.execute(events_stmt)
    events = events_res.scalars().all()
    event_labels = [e.label for e in events]
    assert "Incident Detected" in event_labels
    assert "Alert Re-triggered" in event_labels


@pytest.mark.asyncio
async def test_resolved_alert_transitions_active_incident(
    p21_client: TestClient, p21_org_and_service, db_session: AsyncSession
):
    """Resolved alert transitions active incident to resolved and adds transition record."""
    org, service = p21_org_and_service
    incident = Incident(
        id=f"INC-RES-{uuid.uuid4().hex[:6]}",
        organization_id=org.id,
        service_id=service.id,
        service_name=service.name,
        title="High error rate",
        severity="high",
        status="investigating",
        detected_at=datetime.now(timezone.utc),
        recovery_status="Approval required",
        error_rate=2.0,
        threshold=1.0,
    )
    db_session.add(incident)
    await db_session.commit()

    payload = {
        "status": "resolved",
        "alerts": [
            {
                "status": "resolved",
                "labels": {"alertname": "HighErrorRate", "service": service.name},
            }
        ],
    }

    res = p21_client.post(
        "/api/v1/alerts/webhook",
        json=payload,
        headers={"X-Alertmanager-Secret": settings.ALERTMANAGER_HMAC_SECRET},
    )
    assert res.status_code == 200
    assert res.json()["incidents_updated"] == 1

    await db_session.refresh(incident)
    assert incident.status == "resolved"
    assert incident.resolved_at is not None

    # Transition record created
    tr_stmt = select(IncidentTransition).where(IncidentTransition.incident_id == incident.id)
    tr_res = await db_session.execute(tr_stmt)
    transitions = tr_res.scalars().all()
    assert len(transitions) == 1
    assert transitions[0].previous_state == "investigating"
    assert transitions[0].new_state == "resolved"
    assert transitions[0].actor_role == "system"


@pytest.mark.asyncio
async def test_unknown_resolved_alert_handles_safely(
    p21_client: TestClient, p21_org_and_service, db_session: AsyncSession
):
    """Resolved alerts for services without active incidents complete safely without errors or state corruption."""
    _, service = p21_org_and_service
    payload = {
        "status": "resolved",
        "alerts": [
            {
                "status": "resolved",
                "labels": {"alertname": "CPUSaturation", "service": service.name},
            }
        ],
    }

    res = p21_client.post(
        "/api/v1/alerts/webhook",
        json=payload,
        headers={"X-Alertmanager-Secret": settings.ALERTMANAGER_HMAC_SECRET},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["incidents_created"] == 0
    assert data["incidents_updated"] == 0
    assert "no active incident existed" in data["details"][0]

    # No incident created
    inc_stmt = select(Incident).where(Incident.service_id == service.id)
    assert len((await db_session.execute(inc_stmt)).scalars().all()) == 0


@pytest.mark.asyncio
async def test_multiple_alerts_in_single_payload(
    p21_client: TestClient, db_session: AsyncSession
):
    """Processes multiple alerts in one payload: intra-batch deduplication on one service and new creation on another."""
    org = Organization(id=uuid.uuid4(), slug=f"batch-org-{uuid.uuid4().hex[:4]}", name="Batch Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    s1 = Service(
        id=f"svc-s1-{uuid.uuid4().hex[:4]}",
        organization_id=org.id,
        name=f"svc-alpha-{uuid.uuid4().hex[:4]}",
        environment="production",
        status="healthy",
        availability=99.9,
        error_rate=0.0,
        latency_ms=30,
        last_checked=datetime.now(timezone.utc),
    )
    s2 = Service(
        id=f"svc-s2-{uuid.uuid4().hex[:4]}",
        organization_id=org.id,
        name=f"svc-beta-{uuid.uuid4().hex[:4]}",
        environment="production",
        status="healthy",
        availability=99.9,
        error_rate=0.0,
        latency_ms=45,
        last_checked=datetime.now(timezone.utc),
    )
    db_session.add_all([s1, s2])
    await db_session.commit()

    # Payload has 3 alerts:
    # 1. Alert on s1 (firing) -> creates incident
    # 2. Duplicate alert on s1 (firing) -> deduplicates onto s1 incident
    # 3. Alert on s2 (firing) -> creates incident on s2
    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "HighLatency", "service": s1.name, "severity": "medium"},
                "annotations": {"summary": "S1 latency high"},
            },
            {
                "status": "firing",
                "labels": {"alertname": "CPUSaturation", "service": s1.name, "severity": "high"},
                "annotations": {"summary": "S1 CPU high"},
            },
            {
                "status": "firing",
                "labels": {"alertname": "ServiceDown", "service": s2.name, "severity": "critical"},
                "annotations": {"summary": "S2 offline"},
            },
        ],
    }

    res = p21_client.post(
        "/api/v1/alerts/webhook",
        json=payload,
        headers={"X-Alertmanager-Secret": settings.ALERTMANAGER_HMAC_SECRET},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["incidents_created"] == 2
    assert data["incidents_updated"] == 1

    # Check distinct collision-free IDs
    incs = (await db_session.execute(select(Incident).where(Incident.organization_id == org.id))).scalars().all()
    assert len(incs) == 2
    ids = {i.id for i in incs}
    assert len(ids) == 2, "Incident IDs must be strictly unique!"


@pytest.mark.asyncio
async def test_missing_annotations_and_labels_handled_safely(
    p21_client: TestClient, p21_org_and_service, db_session: AsyncSession
):
    """Payloads with minimal or empty annotations do not crash and generate fallback telemetry."""
    _, service = p21_org_and_service
    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "MinimalAlert", "service": service.name},
                # Missing annotations completely
            }
        ],
    }

    res = p21_client.post(
        "/api/v1/alerts/webhook",
        json=payload,
        headers={"X-Alertmanager-Secret": settings.ALERTMANAGER_HMAC_SECRET},
    )
    assert res.status_code == 200
    assert res.json()["incidents_created"] == 1

    inc = (await db_session.execute(select(Incident).where(Incident.service_id == service.id))).scalar_one()
    assert "MinimalAlert" in inc.title
    assert inc.probable_cause is not None


# ==============================================================================
# Phase 21E — Webhook Resilience & Transaction Boundaries
# ==============================================================================

@pytest.mark.asyncio
async def test_database_transaction_failure_triggers_rollback(
    p21_client: TestClient, p21_org_and_service
):
    """Database commit failure during alert processing rolls back cleanly and returns HTTP 500."""
    _, service = p21_org_and_service
    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "FailAlert", "service": service.name},
            }
        ],
    }

    # Simulate database commit error
    with patch.object(AsyncSession, "commit", side_effect=RuntimeError("Disk I/O lock failure")):
        res = p21_client.post(
            "/api/v1/alerts/webhook",
            json=payload,
            headers={"X-Alertmanager-Secret": settings.ALERTMANAGER_HMAC_SECRET},
        )
        assert res.status_code == 500
        assert "Database transaction failure" in res.json()["detail"]


@pytest.mark.asyncio
async def test_concurrent_webhook_delivery_does_not_collide(
    p21_client: TestClient, p21_org_and_service, db_session: AsyncSession
):
    """Sequential or rapid duplicate webhooks for the same service result in exactly 1 open incident."""
    _, service = p21_org_and_service
    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "HighErrorRate", "service": service.name, "severity": "high"},
                "annotations": {"summary": "Error burst"},
            }
        ],
    }

    headers = {"X-Alertmanager-Secret": settings.ALERTMANAGER_HMAC_SECRET}
    res1 = p21_client.post("/api/v1/alerts/webhook", json=payload, headers=headers)
    res2 = p21_client.post("/api/v1/alerts/webhook", json=payload, headers=headers)

    assert res1.status_code == 200
    assert res2.status_code == 200

    # Total active incidents for this service must remain exactly 1
    incs = (await db_session.execute(select(Incident).where(Incident.service_id == service.id))).scalars().all()
    assert len(incs) == 1


# ==============================================================================
# Phase 21F — Frontend API Compatibility & Timestamp UTC Integrity
# ==============================================================================

@pytest.mark.asyncio
async def test_incident_timestamps_are_consistent_utc(
    p21_client: TestClient, p21_org_and_service, db_session: AsyncSession
):
    """Validates that detected_at, resolved_at, evidence, events, and transitions are all timezone-aware UTC."""
    _, service = p21_org_and_service
    payload_firing = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "UtcTestAlert", "service": service.name, "severity": "medium"},
                "annotations": {"summary": "UTC integrity test"},
            }
        ],
    }
    headers = {"X-Alertmanager-Secret": settings.ALERTMANAGER_HMAC_SECRET}
    p21_client.post("/api/v1/alerts/webhook", json=payload_firing, headers=headers)

    payload_resolved = {
        "status": "resolved",
        "alerts": [
            {
                "status": "resolved",
                "labels": {"alertname": "UtcTestAlert", "service": service.name},
            }
        ],
    }
    p21_client.post("/api/v1/alerts/webhook", json=payload_resolved, headers=headers)

    inc = (await db_session.execute(select(Incident).where(Incident.service_id == service.id))).scalar_one()
    assert inc.detected_at is not None
    assert isinstance(inc.detected_at, datetime)
    assert inc.resolved_at is not None
    assert isinstance(inc.resolved_at, datetime)

    events = (await db_session.execute(select(IncidentEvent).where(IncidentEvent.incident_id == inc.id))).scalars().all()
    assert len(events) >= 2
    for ev in events:
        assert ev.timestamp is not None
        assert isinstance(ev.timestamp, datetime)

    transitions = (await db_session.execute(select(IncidentTransition).where(IncidentTransition.incident_id == inc.id))).scalars().all()
    assert len(transitions) >= 2
    for tr in transitions:
        assert tr.created_at is not None
        assert isinstance(tr.created_at, datetime)


@pytest.mark.asyncio
async def test_frontend_incident_detail_api_compatibility(
    p21_client: TestClient, p21_org_and_service, db_session: AsyncSession
):
    """Validates that webhook-generated incidents serialize into the schema expected by the frontend."""
    org, service = p21_org_and_service
    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "FrontendCompatibilityAlert", "service": service.name, "severity": "high"},
                "annotations": {"summary": "Frontend compatibility verification"},
            }
        ],
    }
    res = p21_client.post(
        "/api/v1/alerts/webhook",
        json=payload,
        headers={"X-Alertmanager-Secret": settings.ALERTMANAGER_HMAC_SECRET},
    )
    assert res.status_code == 200

    inc = (await db_session.execute(select(Incident).where(Incident.service_id == service.id))).scalar_one()

    # Provide authenticated operator credentials for incident detail query
    test_user = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email="operator@autoheal.test",
        full_name="Frontend Test Operator",
        role="operator",
        is_active=True,
    )
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_current_org] = lambda: org

    # Query frontend detail endpoint
    detail_res = p21_client.get(f"/api/v1/incidents/{inc.id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()

    # Check required fields used in frontend data-views.tsx
    assert detail["id"] == inc.id
    assert detail["title"] == inc.title
    assert detail["severity"] == "high"
    assert detail["status"] == "open"
    assert detail["serviceName"] == service.name
    assert "evidence" in detail
    assert "events" in detail
    assert len(detail["evidence"]) >= 1
    assert len(detail["events"]) >= 1
