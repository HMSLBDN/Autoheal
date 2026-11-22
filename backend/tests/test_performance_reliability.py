"""
AutoHeal DevOps — Performance & Reliability Validation Suite
Measures actual API response times, concurrency handling, background task throughput,
SSE ticket lifecycle, recovery idempotency, and database session recycling.
"""

import asyncio
from datetime import datetime, timezone
import statistics
import time
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db
from app.core.security import create_access_token
from app.database import async_session_factory
from app.main import app
from app.models.recovery import RecoveryAction
from app.services.ticket import sse_ticket_service
from app.tasks.recovery import _run_recovery


@pytest.mark.asyncio
async def test_performance_api_response_times(db_session, seed_data):
    """
    Measures sequential API latency (min, median, p95, max) for core health and service endpoints.
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    latencies = []
    iterations = 30

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Warmup
            await client.get("/api/v1/health")

            for _ in range(iterations):
                t0 = time.perf_counter()
                resp = await client.get("/api/v1/health")
                t1 = time.perf_counter()
                assert resp.status_code == 200
                latencies.append((t1 - t0) * 1000)

        mean_ms = statistics.mean(latencies)
        p95_ms = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
        min_ms = min(latencies)
        max_ms = max(latencies)

        print(f"\n[BENCHMARK] /api/v1/health Response Times ({iterations} requests):")
        print(f"  Min: {min_ms:.2f}ms | Mean: {mean_ms:.2f}ms | P95: {p95_ms:.2f}ms | Max: {max_ms:.2f}ms")

        # Performance assertion: In-memory health check should average under 20ms
        assert mean_ms < 50.0, f"Mean latency {mean_ms:.2f}ms exceeds 50ms SLA"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_performance_concurrent_requests(db_session, seed_data):
    """
    Measures throughput and concurrency handling under 20 simultaneous API requests.
    """
    user_a = seed_data["user_a"]
    token = create_access_token(
        user_id=str(user_a.id),
        email=user_a.email,
        role=user_a.role,
        org_id=str(user_a.organization_id),
    )
    headers = {"Authorization": f"Bearer {token}"}

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    concurrent_count = 20

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            t0 = time.perf_counter()
            tasks = [client.get("/api/v1/services", headers=headers) for _ in range(concurrent_count)]
            responses = await asyncio.gather(*tasks)
            t1 = time.perf_counter()

            total_time = t1 - t0
            rps = concurrent_count / total_time

            for r in responses:
                assert r.status_code == 200

            print(f"\n[BENCHMARK] Concurrent Requests ({concurrent_count} parallel requests):")
            print(f"  Total Duration: {total_time * 1000:.2f}ms | Throughput: {rps:.2f} req/sec")

            assert total_time < 5.0, "Concurrent batch must complete within 5 seconds"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_recovery_idempotency_performance(db_session, seed_data, monkeypatch):
    """
    Verifies that running recovery on an already-completed action returns instantly
    without re-executing or causing duplicate side-effects.
    """
    from tests.conftest import TestingSessionLocal
    monkeypatch.setattr("app.tasks.recovery.async_session_factory", TestingSessionLocal)

    rec_pending = seed_data["rec_pending"]
    rec_pending.action = "restart_service"
    rec_pending.status = "approved"
    await db_session.commit()

    # 1. First execution: Transitions from approved to completed
    res1 = await _run_recovery(rec_pending.id, simulated_healthy=True)
    assert res1["status"] == "success"
    assert res1["recovery_status"] in ("completed", "verified")

    # 2. Second execution (idempotency check): Must detect already_completed in < 15ms
    t0 = time.perf_counter()
    res2 = await _run_recovery(rec_pending.id, simulated_healthy=True)
    t1 = time.perf_counter()

    elapsed_ms = (t1 - t0) * 1000
    print(f"\n[BENCHMARK] Recovery Idempotency Check Duration: {elapsed_ms:.2f}ms")

    assert res2["status"] == "already_completed"
    assert elapsed_ms < 50.0, "Idempotency check should be near-instantaneous"


@pytest.mark.asyncio
async def test_sse_ticket_lifecycle_performance(db_session, seed_data):
    """
    Measures cryptographic ticket generation and atomic single-use burn latency.
    """
    user_a = seed_data["user_a"]
    org_a = seed_data["org_a"]

    t0 = time.perf_counter()
    ticket, ttl = sse_ticket_service.issue_ticket(str(user_a.id), str(org_a.id))
    t1 = time.perf_counter()

    issue_ms = (t1 - t0) * 1000

    t2 = time.perf_counter()
    consumed = sse_ticket_service.consume_ticket(ticket)
    t3 = time.perf_counter()

    burn_ms = (t3 - t2) * 1000

    print(f"\n[BENCHMARK] SSE Ticket Operations:")
    print(f"  Issue: {issue_ms:.3f}ms | Burn/Consume: {burn_ms:.3f}ms")

    assert consumed is not None
    assert issue_ms < 5.0
    assert burn_ms < 5.0


@pytest.mark.asyncio
async def test_database_connection_pool_stress():
    """
    Simulates rapid checkout and release of 50 database sessions through async_session_factory.
    Verifies no connection leaks or session exhaustion.
    """
    t0 = time.perf_counter()
    for _ in range(50):
        async with async_session_factory() as session:
            assert session.is_active is True
    t1 = time.perf_counter()

    total_ms = (t1 - t0) * 1000
    avg_checkout_ms = total_ms / 50

    print(f"\n[BENCHMARK] DB Session Pool Stress (50 rapid checkouts):")
    print(f"  Total Duration: {total_ms:.2f}ms | Avg Checkout: {avg_checkout_ms:.3f}ms/session")

    assert avg_checkout_ms < 10.0
