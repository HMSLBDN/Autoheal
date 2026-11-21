"""
AutoHeal DevOps — Pytest Test Configuration & Fixtures
Provides an isolated in-memory async SQLite database and pre-seeded organizations.
"""

import asyncio
from datetime import datetime, timezone
import os
import sys
from typing import AsyncGenerator
import uuid

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("ALERTMANAGER_HMAC_SECRET", "test-env-alertmanager-hmac-secret-32-chars")

from app.api.deps import get_current_org, get_current_user, get_db
from app.config import get_settings
from app.models.base import Base
from app.main import app
from app.models import (
    Incident,
    IncidentEvidence,
    IncidentEvent,
    Organization,
    RecoveryAction,
    RecoveryResult,
    Service,
    ServiceMetric,
    User,
)

settings = get_settings()

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
    """Provides a transactional database session rolled back after every test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def seed_data(db_session: AsyncSession):
    """Seeds two isolated organizations with services, incidents, and recoveries."""
    # Org A
    org_a = Organization(
        id=uuid.uuid4(),
        slug="org-alpha",
        name="Organization Alpha",
        plan="enterprise",
        is_active=True,
    )
    # Org B (for multi-tenant isolation testing)
    org_b = Organization(
        id=uuid.uuid4(),
        slug="org-beta",
        name="Organization Beta",
        plan="starter",
        is_active=True,
    )
    db_session.add_all([org_a, org_b])
    await db_session.flush()

    user_a = User(
        id=uuid.uuid4(),
        organization_id=org_a.id,
        email="operator@org-a.com",
        full_name="Alpha Operator",
        hashed_password="[TEST_HASH]",
        role="operator",
        is_active=True,
    )
    user_b = User(
        id=uuid.uuid4(),
        organization_id=org_b.id,
        email="operator@org-b.com",
        full_name="Beta Operator",
        hashed_password="[TEST_HASH]",
        role="operator",
        is_active=True,
    )
    db_session.add_all([user_a, user_b])
    await db_session.flush()

    # Services for Org A
    svc_a1 = Service(
        id="svc-checkout",
        organization_id=org_a.id,
        name="checkout-api",
        environment="production",
        status="healthy",
        availability=99.98,
        error_rate=0.12,
        latency_ms=142,
        last_checked=datetime.now(timezone.utc),
    )
    svc_a2 = Service(
        id="svc-web",
        organization_id=org_a.id,
        name="customer-web",
        environment="staging",
        status="degraded",
        availability=98.50,
        error_rate=1.84,
        latency_ms=450,
        last_checked=datetime.now(timezone.utc),
    )

    # Service for Org B
    svc_b1 = Service(
        id="svc-beta-payments",
        organization_id=org_b.id,
        name="payments-api",
        environment="production",
        status="healthy",
        availability=99.99,
        error_rate=0.01,
        latency_ms=50,
        last_checked=datetime.now(timezone.utc),
    )
    db_session.add_all([svc_a1, svc_a2, svc_b1])
    await db_session.flush()

    # Incidents for Org A
    inc_a1 = Incident(
        id="INC-1001",
        organization_id=org_a.id,
        service_id=svc_a2.id,
        service_name=svc_a2.name,
        title="Elevated Error Rate",
        severity="high",
        status="open",
        detected_at=datetime.now(timezone.utc),
        recovery_status="Approval required",
        error_rate=1.84,
        threshold=1.0,
        probable_cause="Upstream gateway timeout",
        recommended_action="Rollback deployment",
    )
    inc_a2_resolved = Incident(
        id="INC-1002",
        organization_id=org_a.id,
        service_id=svc_a1.id,
        service_name=svc_a1.name,
        title="Resolved Database Blip",
        severity="low",
        status="resolved",
        detected_at=datetime.now(timezone.utc),
        recovery_status="Verified",
        error_rate=0.2,
        threshold=1.0,
        probable_cause="Transient reset",
        recommended_action="None",
        resolved_at=datetime.now(timezone.utc),
    )

    # Incident for Org B
    inc_b1 = Incident(
        id="INC-9999",
        organization_id=org_b.id,
        service_id=svc_b1.id,
        service_name=svc_b1.name,
        title="Beta Org Incident",
        severity="critical",
        status="open",
        detected_at=datetime.now(timezone.utc),
        recovery_status="Not started",
        error_rate=4.5,
        threshold=2.0,
        probable_cause="Queue overflow",
        recommended_action="Scale consumer",
    )
    db_session.add_all([inc_a1, inc_a2_resolved, inc_b1])
    await db_session.flush()

    # Evidence & Event for inc_a1
    ev_a1 = IncidentEvidence(
        id="ev-1",
        incident_id=inc_a1.id,
        kind="metric",
        title="Error threshold exceeded",
        detail="1.84% > 1.0%",
        timestamp=datetime.now(timezone.utc),
    )
    event_a1 = IncidentEvent(
        id="e1",
        incident_id=inc_a1.id,
        label="Incident detected",
        detail="Threshold crossed",
        tone="warning",
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add_all([ev_a1, event_a1])

    # Recoveries for Org A
    rec_pending = RecoveryAction(
        id="REC-101",
        incident_id=inc_a1.id,
        service_id=svc_a2.id,
        service_name=svc_a2.name,
        action="Rollback to previous release",
        status="pending_approval",
        approval_required=True,
        requested_by="AutoHeal policy",
        requested_at=datetime.now(timezone.utc),
        verification="pending",
    )
    rec_completed = RecoveryAction(
        id="REC-102",
        incident_id=inc_a2_resolved.id,
        service_id=svc_a1.id,
        service_name=svc_a1.name,
        action="Tune connection pool",
        status="completed",
        approval_required=True,
        requested_by="Alex Chen",
        requested_at=datetime.now(timezone.utc),
        duration_seconds=35,
        verification="passed",
    )
    db_session.add_all([rec_pending, rec_completed])
    await db_session.flush()

    rec_result = RecoveryResult(
        id=uuid.uuid4(),
        recovery_action_id=rec_completed.id,
        verified=True,
        summary="Pool saturation normalized.",
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(rec_result)

    await db_session.commit()

    return {
        "org_a": org_a,
        "org_b": org_b,
        "user_a": user_a,
        "user_b": user_b,
        "svc_a1": svc_a1,
        "svc_a2": svc_a2,
        "svc_b1": svc_b1,
        "inc_a1": inc_a1,
        "inc_a2_resolved": inc_a2_resolved,
        "inc_b1": inc_b1,
        "rec_pending": rec_pending,
        "rec_completed": rec_completed,
    }


@pytest.fixture
def client(db_session: AsyncSession, seed_data: dict) -> TestClient:
    """Returns a TestClient scoped by default to Organization Alpha with Operator credentials."""
    org_a = seed_data["org_a"]
    user_a = seed_data["user_a"]

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return user_a

    async def override_get_current_org():
        return org_a

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_org] = override_get_current_org

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
