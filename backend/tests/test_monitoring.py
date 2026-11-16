"""
AutoHeal DevOps — Monitoring & Telemetry Test Suite
Verifies Prometheus metric queries, HTTP health probes, timeout handling,
unavailable service degradation, and background collection passes.
"""

from datetime import datetime, timezone
import uuid
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.service import Service, ServiceMonitor
from app.services.monitoring import MonitoringService


@pytest.mark.asyncio
async def test_monitoring_cycle_with_healthy_service(db_session: AsyncSession):
    """Monitoring service scrapes registered services, records metric rows, and updates last_checked."""
    org = Organization(id=uuid.uuid4(), slug="mon-org", name="Mon Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    svc = Service(
        id="svc-mon-test",
        organization_id=org.id,
        name="checkout-api",
        environment="production",
        status="healthy",
        availability=99.9,
        error_rate=0.05,
        latency_ms=120,
        last_checked=datetime.now(timezone.utc),
    )
    monitor = ServiceMonitor(
        id=uuid.uuid4(),
        service_id=svc.id,
        health_check_path="/health",
        metrics_path="/metrics",
        timeout_seconds=2.0,
    )
    db_session.add_all([svc, monitor])
    await db_session.commit()

    mon_service = MonitoringService()
    metrics = await mon_service.run_monitoring_cycle(db_session)

    assert len(metrics) >= 1
    sample = metrics[0]
    assert sample.service_id == svc.id
    assert sample.error_rate >= 0.0
    assert sample.availability > 0.0


@pytest.mark.asyncio
async def test_monitoring_unavailable_service_handled_safely(db_session: AsyncSession):
    """When a service endpoint is offline or refused, monitoring safely catches exception without crashing."""
    org = Organization(id=uuid.uuid4(), slug="unavail-org", name="Unavail Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    svc = Service(
        id="svc-offline",
        organization_id=org.id,
        name="nonexistent-dead-service",
        environment="staging",
        status="healthy",
        availability=99.9,
        error_rate=0.1,
        latency_ms=100,
        last_checked=datetime.now(timezone.utc),
    )
    db_session.add(svc)
    await db_session.commit()

    mon_service = MonitoringService()
    # probe_service should not raise an unhandled exception
    snapshot = await mon_service.probe_service(svc)
    assert snapshot.service_id == svc.id
    assert snapshot.is_reachable is False


@pytest.mark.asyncio
async def test_monitoring_timeout_handling(db_session: AsyncSession):
    """Slow service probe respecting timeout parameter."""
    org = Organization(id=uuid.uuid4(), slug="timeout-org", name="Timeout Org", is_active=True)
    db_session.add(org)
    await db_session.flush()

    svc = Service(
        id="svc-slow",
        organization_id=org.id,
        name="slow-service",
        environment="production",
        status="healthy",
        availability=99.9,
        error_rate=0.0,
        latency_ms=50,
        last_checked=datetime.now(timezone.utc),
    )
    monitor = ServiceMonitor(
        id=uuid.uuid4(),
        service_id=svc.id,
        timeout_seconds=0.001,  # Ultra-low timeout to trigger timeout handling
    )
    db_session.add_all([svc, monitor])
    await db_session.commit()

    mon_service = MonitoringService()
    snapshot = await mon_service.probe_service(svc, monitor=monitor)
    assert snapshot.is_reachable is False
