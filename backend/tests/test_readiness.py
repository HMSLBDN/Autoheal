"""
AutoHeal DevOps — Health, Liveness & Readiness Probes Tests
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoints(db_session: AsyncSession):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Public health probe
            health_resp = await client.get("/api/v1/health")
            assert health_resp.status_code == 200
            assert health_resp.json()["status"] == "healthy"

            # Liveness probe
            live_resp = await client.get("/api/v1/health/liveness")
            assert live_resp.status_code == 200
            assert live_resp.json()["status"] == "alive"

            # Deep readiness probe
            ready_resp = await client.get("/api/v1/health/readiness")
            assert ready_resp.status_code in (200, 503)
            body = ready_resp.json()
            assert "components" in body
            assert "database" in body["components"]
            assert "redis" in body["components"]
            assert body["components"]["database"] == "healthy"
    finally:
        app.dependency_overrides.clear()
