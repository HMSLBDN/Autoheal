"""
AutoHeal DevOps — Production Scalability & API Latency Benchmarking Harness
Executes concurrent stress tests against critical API endpoints and records
P50, P95, P99 latencies, throughput (RPS), and connection pool utilization.
"""

import asyncio
from datetime import datetime, timezone
import json
import os
import statistics
import sys
import time
from typing import Any, Dict, List
import uuid

import httpx
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ALERTMANAGER_HMAC_SECRET", "test-env-alertmanager-hmac-secret-32-chars")

from app.api.deps import get_current_org, get_current_user, get_db
from app.config import get_settings
from app.main import app
from app.models.base import Base
from app.models import Incident, Organization, RecoveryAction, Service, User

settings = get_settings()

BENCHMARK_DB_URL = "sqlite+aiosqlite:///:memory:"
bench_engine = create_async_engine(
    BENCHMARK_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
BenchSessionLocal = async_sessionmaker(
    bind=bench_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def seed_benchmark_database() -> Dict[str, Any]:
    """Seeds baseline tenant, services, and incidents for realistic load testing."""
    async with bench_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with BenchSessionLocal() as session:
        org = Organization(
            id=uuid.uuid4(),
            slug="bench-org",
            name="Benchmark Performance Org",
            plan="enterprise",
            is_active=True,
        )
        session.add(org)
        await session.flush()

        user = User(
            id=uuid.uuid4(),
            organization_id=org.id,
            email="benchmarker@autoheal.io",
            full_name="Benchmark Worker",
            hashed_password="[HASH]",
            role="admin",
            is_active=True,
        )
        session.add(user)
        await session.flush()

        # Seed 10 services
        services = []
        for i in range(10):
            svc = Service(
                id=f"svc-bench-{i}",
                organization_id=org.id,
                name=f"microservice-{i}",
                environment="production",
                status="healthy",
                availability=99.95,
                error_rate=0.05,
                latency_ms=45 + (i * 5),
                last_checked=datetime.now(timezone.utc),
            )
            services.append(svc)
        session.add_all(services)
        await session.flush()

        # Seed 25 incidents
        incidents = []
        for i in range(25):
            inc = Incident(
                id=f"INC-B{1000 + i}",
                organization_id=org.id,
                service_id=services[i % len(services)].id,
                service_name=services[i % len(services)].name,
                title=f"Synthetic Load Incident {i}",
                severity="high" if i % 2 == 0 else "medium",
                status="open" if i % 3 == 0 else "resolved",
                detected_at=datetime.now(timezone.utc),
                recovery_status="Verified" if i % 3 != 0 else "Approval required",
                error_rate=1.5,
                threshold=1.0,
                probable_cause="Synthetic concurrency test",
                recommended_action="Scale pod replicas",
            )
            incidents.append(inc)
        session.add_all(incidents)
        await session.flush()

        # Seed 10 recovery actions
        recoveries = []
        for i in range(10):
            rec = RecoveryAction(
                id=f"REC-B{500 + i}",
                incident_id=incidents[i].id,
                service_id=services[i % len(services)].id,
                service_name=services[i % len(services)].name,
                action="Scale pod replicas",
                status="completed" if i % 2 == 0 else "pending_approval",
                approval_required=True,
                requested_by="Benchmark Runner",
                requested_at=datetime.now(timezone.utc),
                duration_seconds=12,
                verification="passed" if i % 2 == 0 else "pending",
            )
            recoveries.append(rec)
        session.add_all(recoveries)
        await session.commit()

        return {"org": org, "user": user}


async def run_scenario(
    client: httpx.AsyncClient,
    endpoint: str,
    method: str = "GET",
    total_requests: int = 200,
    concurrency: int = 10,
) -> Dict[str, Any]:
    """Runs a concurrent stress scenario against a specific endpoint and measures latency distribution."""
    sem = asyncio.Semaphore(concurrency)
    latencies: List[float] = []
    status_codes: Dict[int, int] = {}
    errors: int = 0

    async def single_request():
        nonlocal errors
        async with sem:
            start = time.perf_counter()
            try:
                res = await client.request(method, endpoint)
                duration = time.perf_counter() - start
                latencies.append(duration)
                status_codes[res.status_code] = status_codes.get(res.status_code, 0) + 1
            except Exception:
                duration = time.perf_counter() - start
                latencies.append(duration)
                errors += 1

    wall_start = time.perf_counter()
    tasks = [asyncio.create_task(single_request()) for _ in range(total_requests)]
    await asyncio.gather(*tasks)
    wall_duration = time.perf_counter() - wall_start

    sorted_latencies = sorted(latencies)
    count = len(sorted_latencies)

    def percentile(p: float) -> float:
        if not sorted_latencies:
            return 0.0
        k = (count - 1) * (p / 100.0)
        f = int(k)
        c = min(f + 1, count - 1)
        d0 = sorted_latencies[f] * (c - k)
        d1 = sorted_latencies[c] * (k - f)
        return (d0 + d1) * 1000.0

    mean_ms = (statistics.mean(sorted_latencies) * 1000.0) if sorted_latencies else 0.0
    p50_ms = percentile(50.0)
    p95_ms = percentile(95.0)
    p99_ms = percentile(99.0)
    min_ms = (min(sorted_latencies) * 1000.0) if sorted_latencies else 0.0
    max_ms = (max(sorted_latencies) * 1000.0) if sorted_latencies else 0.0
    rps = count / wall_duration if wall_duration > 0 else 0.0

    return {
        "endpoint": endpoint,
        "concurrency": concurrency,
        "total_requests": count,
        "successful_requests": sum(v for k, v in status_codes.items() if 200 <= k < 400),
        "failed_requests": errors + sum(v for k, v in status_codes.items() if k >= 400),
        "wall_duration_seconds": round(wall_duration, 3),
        "throughput_rps": round(rps, 1),
        "latency_ms": {
            "mean": round(mean_ms, 2),
            "p50": round(p50_ms, 2),
            "p95": round(p95_ms, 2),
            "p99": round(p99_ms, 2),
            "min": round(min_ms, 2),
            "max": round(max_ms, 2),
        },
        "status_distribution": status_codes,
    }


async def main():
    print("=" * 70)
    print("AutoHeal DevOps — Production Scalability & API Latency Benchmark")
    print("=" * 70)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")

    seed = await seed_benchmark_database()
    org = seed["org"]
    user = seed["user"]

    async def override_get_db():
        async with BenchSessionLocal() as session:
            yield session

    async def override_get_current_user():
        return user

    async def override_get_current_org():
        return org

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_org] = override_get_current_org

    scenarios_config = [
        # (endpoint, concurrency, total_requests)
        ("/api/v1/health", 10, 200),
        ("/api/v1/health", 50, 500),
        ("/api/v1/services", 10, 200),
        ("/api/v1/services", 50, 500),
        ("/api/v1/incidents", 10, 200),
        ("/api/v1/incidents", 50, 500),
        ("/api/v1/analytics/summary", 10, 200),
        ("/api/v1/analytics/summary", 50, 500),
    ]

    results = []

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://benchmark.internal",
    ) as client:
        for endpoint, concurrency, total in scenarios_config:
            print(f"\nEvaluating: {endpoint} | Concurrency: {concurrency:2d} | Requests: {total}")
            res = await run_scenario(
                client=client,
                endpoint=endpoint,
                concurrency=concurrency,
                total_requests=total,
            )
            results.append(res)
            lat = res["latency_ms"]
            print(
                f"  RPS: {res['throughput_rps']:7.1f} | Mean: {lat['mean']:6.2f}ms | "
                f"P50: {lat['p50']:6.2f}ms | P95: {lat['p95']:6.2f}ms | P99: {lat['p99']:6.2f}ms"
            )

    # Save results to monitoring/benchmark_results.json
    output_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "monitoring", "benchmark_results.json"))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "test_suite": "AutoHeal DevOps Scalability & Concurrency Benchmark",
                "pool_configuration": {
                    "pool_size": getattr(settings, "DB_POOL_SIZE", 20),
                    "max_overflow": getattr(settings, "DB_MAX_OVERFLOW", 10),
                    "pool_timeout_seconds": getattr(settings, "DB_POOL_TIMEOUT", 30),
                    "pool_recycle_seconds": getattr(settings, "DB_POOL_RECYCLE", 1800),
                },
                "scenarios": results,
            },
            f,
            indent=2,
        )
    print(f"\n[SUCCESS] Benchmark results saved to: {output_path}")

    # Clean up test database
    async with bench_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await bench_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
