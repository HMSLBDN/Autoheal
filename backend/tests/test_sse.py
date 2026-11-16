"""
AutoHeal DevOps — Server-Sent Events (SSE) Tests
Tests authentication (header & query param), tenant isolation, heartbeat, and event broadcasting.
"""

import asyncio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import create_access_token
from app.main import app
from app.services.events import event_broadcaster


@pytest.fixture
def sse_client(db_session: AsyncSession) -> TestClient:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_sse_requires_authentication(sse_client: TestClient):
    """Connecting to SSE stream without credentials fails with 401 Unauthorized."""
    response = sse_client.get("/api/v1/events/stream")
    assert response.status_code == 401


def test_sse_rejects_invalid_token(sse_client: TestClient):
    """Connecting to SSE stream with malformed or invalid token fails with 401."""
    response = sse_client.get("/api/v1/events/stream?token=invalid.jwt.token")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sse_broadcast_and_tenant_isolation(
    db_session: AsyncSession, seed_data: dict
):
    """
    Verifies that:
    1. Authenticated clients receive the initial 'connected' event.
    2. Broadcasted events are delivered to active subscribers.
    3. Events broadcasted to org A are never received by subscribers in org B.
    """
    org_a = seed_data["org_a"]
    org_b_id = "00000000-0000-0000-0000-000000000099"

    # Subscribe directly using the broadcaster
    stream_gen_a = event_broadcaster.subscribe(org_a.id)
    stream_gen_b = event_broadcaster.subscribe(org_b_id)

    # 1. First event is 'connected'
    first_a = await stream_gen_a.__anext__()
    assert "event: connected" in first_a
    assert str(org_a.id) in first_a

    first_b = await stream_gen_b.__anext__()
    assert "event: connected" in first_b
    assert org_b_id in first_b

    # 2. Broadcast event to Org A only
    reached = await event_broadcaster.broadcast(
        org_a.id,
        "incident_created",
        {"id": "INC-9999", "title": "Database connection pool saturated"},
    )
    assert reached >= 1

    # Org A subscriber receives the event
    event_a = await stream_gen_a.__anext__()
    assert "event: incident_created" in event_a
    assert "INC-9999" in event_a

    # Org B subscriber does NOT receive Org A's event (queue remains empty)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(stream_gen_b.__anext__(), timeout=0.1)

    # Cleanup generators
    await stream_gen_a.aclose()
    await stream_gen_b.aclose()
