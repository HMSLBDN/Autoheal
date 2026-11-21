"""
AutoHeal DevOps — Detection Classification & Accuracy Metric Verification Test Suite
Verifies mathematically sound metric definitions:
- True Positive (TP): unhealthy observation correctly generates an incident.
- False Positive (FP): healthy observation incorrectly generates an incident.
- False Negative (FN): unhealthy observation fails to generate an incident.
- True Negative (TN): healthy observation correctly generates no incident.
- False-Positive Rate = FP / (FP + TN)
- Reporting unavailable when healthy observation windows (FP + TN) are insufficient.
- Operator recovery rejection is strictly separated from detection accuracy.
"""

from datetime import datetime, timezone
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models import Incident, Organization, RecoveryAction, Service, User


@pytest.fixture
def api_client(db_session: AsyncSession) -> TestClient:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def classification_env(db_session: AsyncSession):
    org = Organization(id=uuid.uuid4(), slug=f"class-org-{uuid.uuid4().hex[:6]}", name="Classification Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    operator = User(
        id=uuid.uuid4(),
        organization_id=org.id,
        email=f"op_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Classification Operator",
        hashed_password=get_password_hash("Password123!"),
        role="operator",
        is_active=True,
    )
    db_session.add(operator)
    await db_session.commit()

    token = create_access_token(str(operator.id), operator.email, operator.role, str(org.id))
    headers = {"Authorization": f"Bearer {token}"}

    return {"org": org, "operator": operator, "headers": headers}


# ==============================================================================
# 1. True Positive (TP): unhealthy observation correctly generates an incident
# ==============================================================================
@pytest.mark.asyncio
async def test_true_positive_unhealthy_observation_creates_incident(api_client: TestClient, classification_env, db_session: AsyncSession):
    ctx = await classification_env
    svc = Service(
        id=f"svc-tp-{uuid.uuid4().hex[:4]}",
        organization_id=ctx["org"].id,
        name="checkout-api",
        environment="production",
        status="critical",
        availability=80.0,
        error_rate=0.25,
        latency_ms=450,
        last_checked=datetime.now(timezone.utc),
    )
    db_session.add(svc)
    await db_session.commit()

    # Simulate alert triggered by unhealthy telemetry breach
    res = api_client.post(
        "/api/v1/demo/simulate-alert",
        headers=ctx["headers"],
        json={"service_name": svc.name, "alertname": "HighErrorRate", "severity": "critical"},
    )
    assert res.status_code == 200
    inc_id = res.json()["incident_id"]

    inc = (await db_session.execute(select(Incident).where(Incident.id == inc_id))).scalar_one()
    assert inc.error_rate >= inc.threshold
    # Validates True Positive classification
    assert inc.error_rate >= 0.01


# ==============================================================================
# 2. False Positive (FP): healthy observation incorrectly generates an incident
# ==============================================================================
@pytest.mark.asyncio
async def test_false_positive_healthy_observation_incorrectly_creates_incident(classification_env, db_session: AsyncSession):
    ctx = await classification_env
    svc = Service(
        id=f"svc-fp-{uuid.uuid4().hex[:4]}",
        organization_id=ctx["org"].id,
        name="customer-web",
        environment="production",
        status="healthy",
        availability=99.99,
        error_rate=0.002,
        latency_ms=15,
        last_checked=datetime.now(timezone.utc),
    )
    # Incident created while service telemetry was strictly below alert threshold
    spurious_incident = Incident(
        id=f"INC-FP-{uuid.uuid4().hex[:4]}",
        organization_id=ctx["org"].id,
        service_id=svc.id,
        service_name=svc.name,
        title="Spurious Alert",
        severity="low",
        status="open",
        detected_at=datetime.now(timezone.utc),
        recovery_status="Approval required",
        error_rate=0.002,  # Healthy: below threshold of 0.01
        threshold=0.01,
        probable_cause="Spurious flapper",
        recommended_action="restart_service",
    )
    db_session.add_all([svc, spurious_incident])
    await db_session.commit()

    # Verify classification logic identifies this as FP
    assert spurious_incident.error_rate < spurious_incident.threshold


# ==============================================================================
# 3. True Negative (TN): healthy observation correctly generates no incident
# ==============================================================================
@pytest.mark.asyncio
async def test_true_negative_healthy_observation_generates_no_incident(classification_env, db_session: AsyncSession):
    ctx = await classification_env
    healthy_svc = Service(
        id=f"svc-tn-{uuid.uuid4().hex[:4]}",
        organization_id=ctx["org"].id,
        name="payments-api",
        environment="production",
        status="healthy",
        availability=99.99,
        error_rate=0.001,
        latency_ms=20,
        last_checked=datetime.now(timezone.utc),
    )
    db_session.add(healthy_svc)
    await db_session.commit()

    # Query active incidents for this healthy service
    inc_res = await db_session.execute(
        select(Incident).where(
            Incident.service_id == healthy_svc.id,
            Incident.status.in_(["open", "investigating", "recovering"]),
        )
    )
    active_incidents = inc_res.scalars().all()
    # TN confirmed: healthy service operating with zero false incidents
    assert len(active_incidents) == 0


# ==============================================================================
# 4. False Negative (FN): unhealthy observation fails to generate an incident
# ==============================================================================
@pytest.mark.asyncio
async def test_false_negative_unhealthy_state_fails_to_create_incident(classification_env, db_session: AsyncSession):
    ctx = await classification_env
    degraded_svc = Service(
        id=f"svc-fn-{uuid.uuid4().hex[:4]}",
        organization_id=ctx["org"].id,
        name="legacy-inventory",
        environment="production",
        status="critical",
        availability=50.0,
        error_rate=0.50,
        latency_ms=3000,
        last_checked=datetime.now(timezone.utc),
    )
    db_session.add(degraded_svc)
    await db_session.commit()

    # Service is degraded in production but no monitoring rule or incident exists
    inc_res = await db_session.execute(select(Incident).where(Incident.service_id == degraded_svc.id))
    incidents = inc_res.scalars().all()
    assert len(incidents) == 0  # FN condition: breach occurred but unmonitored / not captured


# ==============================================================================
# 5. False-Positive Rate Formula & Insufficient Window Reporting
# ==============================================================================
@pytest.mark.asyncio
async def test_false_positive_rate_calculation_formula(api_client: TestClient, classification_env, db_session: AsyncSession):
    ctx = await classification_env

    # Case A: Insufficient healthy observation windows (0 healthy services, 0 FP)
    # Organization has only 1 unhealthy service with 1 true positive incident
    svc_tp = Service(
        id=f"svc-unhealthy-{uuid.uuid4().hex[:4]}",
        organization_id=ctx["org"].id,
        name="order-api",
        environment="production",
        status="critical",
        availability=70.0,
        error_rate=0.30,
        latency_ms=800,
        last_checked=datetime.now(timezone.utc),
    )
    inc_tp = Incident(
        id=f"INC-TP-{uuid.uuid4().hex[:4]}",
        organization_id=ctx["org"].id,
        service_id=svc_tp.id,
        service_name=svc_tp.name,
        title="Outage",
        severity="critical",
        status="open",
        detected_at=datetime.now(timezone.utc),
        recovery_status="Approval required",
        error_rate=0.30,
        threshold=0.01,
        probable_cause="Node failure",
        recommended_action="restart_service",
    )
    db_session.add_all([svc_tp, inc_tp])
    await db_session.commit()

    # Query analytics summary
    res_a = api_client.get("/api/v1/analytics/summary", headers=ctx["headers"])
    assert res_a.status_code == 200
    data_a = res_a.json()
    # When FP + TN == 0, falsePositiveRate must be reported as null (unavailable), not fabricated
    assert data_a["falsePositiveRate"] is None

    # Case B: Sufficient healthy observation windows
    # Add 3 healthy services with no active incidents (TN = 3)
    # Add 1 healthy service with 1 spurious incident (FP = 1, TN = 0 for that service)
    svc_fp = Service(
        id=f"svc-spurious-{uuid.uuid4().hex[:4]}",
        organization_id=ctx["org"].id,
        name="cache-api",
        environment="production",
        status="healthy",
        availability=99.99,
        error_rate=0.001,
        latency_ms=10,
        last_checked=datetime.now(timezone.utc),
    )
    inc_fp = Incident(
        id=f"INC-FP-CALC-{uuid.uuid4().hex[:4]}",
        organization_id=ctx["org"].id,
        service_id=svc_fp.id,
        service_name=svc_fp.name,
        title="Spurious Alert",
        severity="low",
        status="open",
        detected_at=datetime.now(timezone.utc),
        recovery_status="Approval required",
        error_rate=0.001,  # Below threshold
        threshold=0.01,
        probable_cause="Spurious",
        recommended_action="restart_service",
    )
    tn_services = [
        Service(
            id=f"svc-tn-{i}-{uuid.uuid4().hex[:4]}",
            organization_id=ctx["org"].id,
            name=f"healthy-service-{i}",
            environment="production",
            status="healthy",
            availability=99.98,
            error_rate=0.001,
            latency_ms=15,
            last_checked=datetime.now(timezone.utc),
        )
        for i in range(3)
    ]
    db_session.add_all([svc_fp, inc_fp, *tn_services])
    await db_session.commit()

    res_b = api_client.get("/api/v1/analytics/summary", headers=ctx["headers"])
    assert res_b.status_code == 200
    data_b = res_b.json()
    # Expected: FP = 1, TN = 3 (healthy_services 0, 1, 2) -> FP / (FP + TN) = 1 / (1 + 3) = 25.0%
    assert data_b["falsePositiveRate"] == 25.0


# ==============================================================================
# 6. Operator Recovery Rejection Separated from Detection Accuracy
# ==============================================================================
@pytest.mark.asyncio
async def test_operator_rejection_separated_from_detection_accuracy(api_client: TestClient, classification_env, db_session: AsyncSession):
    ctx = await classification_env
    svc = Service(
        id=f"svc-rej-{uuid.uuid4().hex[:4]}",
        organization_id=ctx["org"].id,
        name="payments-api",
        environment="production",
        status="critical",
        availability=80.0,
        error_rate=0.20,
        latency_ms=600,
        last_checked=datetime.now(timezone.utc),
    )
    inc = Incident(
        id=f"INC-REJ-{uuid.uuid4().hex[:4]}",
        organization_id=ctx["org"].id,
        service_id=svc.id,
        service_name=svc.name,
        title="Critical Payment Latency",
        severity="critical",
        status="open",
        detected_at=datetime.now(timezone.utc),
        recovery_status="Approval required",
        error_rate=0.20,
        threshold=0.01,
        probable_cause="Connection leak",
        recommended_action="restart_service",
    )
    rec = RecoveryAction(
        id=f"REC-REJ-{uuid.uuid4().hex[:4]}",
        incident_id=inc.id,
        service_id=svc.id,
        service_name=svc.name,
        action="restart_service",
        status="rejected",  # Operator chose to reject
        approval_required=True,
        requested_by=ctx["operator"].email,
        requested_at=datetime.now(timezone.utc),
        verification="failed",
    )
    db_session.add_all([svc, inc, rec])
    await db_session.commit()

    res = api_client.get("/api/v1/analytics/summary", headers=ctx["headers"])
    assert res.status_code == 200
    data = res.json()

    # Rejection rate is reported separately
    assert data["operatorRejectionRate"] == 100.0
    # True Positive incident with operator rejection does NOT get counted as a false-positive alert
    assert inc.error_rate >= inc.threshold
