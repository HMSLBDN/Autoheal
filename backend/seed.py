"""
AutoHeal DevOps — Idempotent Database Seeder
"""

import asyncio
from datetime import datetime, timezone
import logging
import os
import sys
import uuid
from typing import Optional

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure backend directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import get_settings
from app.database import async_session_factory
from app.models import (
    AlertConfig,
    Incident,
    IncidentEvent,
    IncidentEvidence,
    Organization,
    RecoveryAction,
    RecoveryPolicy,
    RecoveryResult,
    Service,
    ServiceMetric,
    ServiceMonitor,
    User,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


async def seed_organization(session: AsyncSession) -> Organization:
    """Creates default organization if not present."""
    result = await session.execute(
        select(Organization).where(Organization.slug == settings.DEFAULT_ORGANIZATION_SLUG)
    )
    org = result.scalar_one_or_none()
    if not org:
        org = Organization(
            id=uuid.uuid4(),
            slug=settings.DEFAULT_ORGANIZATION_SLUG,
            name=settings.DEFAULT_ORGANIZATION_NAME,
            plan="enterprise",
            is_active=True,
        )
        session.add(org)
        await session.flush()
        logger.info("Created default organization: %s (%s)", org.name, org.slug)
    else:
        logger.info("Organization already exists: %s", org.slug)
    return org


async def seed_admin_user(session: AsyncSession, org: Organization) -> Optional[User]:
    """
    Creates an initial admin user ONLY if credentials are provided via environment variables.
    Never uses a hardcoded password.
    """
    admin_email = os.getenv("INITIAL_ADMIN_EMAIL")
    admin_password = os.getenv("INITIAL_ADMIN_PASSWORD")

    if not admin_email or not admin_password:
        logger.info("INITIAL_ADMIN_EMAIL or INITIAL_ADMIN_PASSWORD not set; skipping admin creation.")
        return None

    result = await session.execute(select(User).where(User.email == admin_email))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            id=uuid.uuid4(),
            organization_id=org.id,
            email=admin_email,
            full_name=os.getenv("INITIAL_ADMIN_NAME", "AutoHeal Administrator"),
            hashed_password=pwd_context.hash(admin_password),
            role="admin",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        logger.info("Created initial admin user: %s", admin_email)
    else:
        logger.info("Admin user already exists: %s", admin_email)
    return user


async def seed_services(session: AsyncSession, org: Organization) -> None:
    """Seeds baseline infrastructure services matching frontend demo inventory."""
    services_data = [
        {"id": "svc-api", "name": "checkout-api", "environment": "production", "status": "healthy", "availability": 99.98, "error_rate": 0.12, "latency_ms": 142},
        {"id": "svc-web", "name": "customer-web", "environment": "production", "status": "degraded", "availability": 99.72, "error_rate": 1.84, "latency_ms": 684},
        {"id": "svc-worker", "name": "event-worker", "environment": "production", "status": "healthy", "availability": 99.95, "error_rate": 0.08, "latency_ms": 86},
        {"id": "svc-pg", "name": "primary-postgres", "environment": "production", "status": "healthy", "availability": 99.99, "error_rate": 0.01, "latency_ms": 21},
        {"id": "svc-search", "name": "search-indexer", "environment": "staging", "status": "critical", "availability": 96.21, "error_rate": 5.40, "latency_ms": 1208},
    ]

    for item in services_data:
        result = await session.execute(select(Service).where(Service.id == item["id"]))
        service = result.scalar_one_or_none()
        if not service:
            service = Service(
                id=item["id"],
                organization_id=org.id,
                name=item["name"],
                environment=item["environment"],
                status=item["status"],
                availability=item["availability"],
                error_rate=item["error_rate"],
                latency_ms=item["latency_ms"],
                last_checked=datetime.now(timezone.utc),
            )
            session.add(service)

            # Add default monitor
            session.add(ServiceMonitor(
                id=uuid.uuid4(),
                service_id=service.id,
                metrics_path="/metrics",
                health_check_path="/healthz",
                scrape_interval_seconds=15,
                timeout_seconds=5,
            ))

            # Add default alert config
            session.add(AlertConfig(
                id=uuid.uuid4(),
                service_id=service.id,
                metric_name="error_rate",
                condition="gt",
                threshold=1.0 if item["environment"] == "production" else 2.0,
                window_seconds=120,
                severity="critical" if item["status"] == "critical" else "high",
            ))

            # Add recovery policy
            session.add(RecoveryPolicy(
                id=uuid.uuid4(),
                service_id=service.id,
                action="rollback_deployment",
                approval_required=True,
                cooldown_seconds=900,
                max_retries=2,
            ))
            logger.info("Seeded service: %s (%s)", service.name, service.id)

    await session.flush()


async def seed_incidents(session: AsyncSession, org: Organization) -> None:
    """Seeds baseline incidents, evidence, and events."""
    incidents_data = [
        {
            "id": "INC-2841",
            "service_id": "svc-web",
            "service_name": "customer-web",
            "title": "Elevated API error rate",
            "severity": "high",
            "status": "investigating",
            "recovery_status": "Approval required",
            "error_rate": 1.84,
            "threshold": 1.0,
            "probable_cause": "A new upstream payment dependency is returning intermittent 5xx responses.",
            "recommended_action": "Shift traffic to the previous stable release and verify checkout health.",
            "evidence": [
                {"id": "ev-1", "kind": "metric", "title": "5xx rate above threshold", "detail": "1.84% over the last 5 minutes (threshold 1.0%)"},
                {"id": "ev-2", "kind": "deployment", "title": "Release deployed", "detail": "release-2026.11.08.3 deployed 8 minutes before alert"},
                {"id": "ev-3", "kind": "log", "title": "Upstream timeout pattern", "detail": "18 matching timeout events on payment-provider"},
            ],
            "events": [
                {"id": "e1", "label": "Incident detected", "detail": "Error rate crossed the configured 1.0% threshold.", "tone": "warning"},
                {"id": "e2", "label": "Diagnosis completed", "detail": "Three signals correlate with the latest release.", "tone": "neutral"},
                {"id": "e3", "label": "Recovery awaiting approval", "detail": "Rollback recommendation requires an operator.", "tone": "neutral"},
            ],
        },
        {
            "id": "INC-2838",
            "service_id": "svc-search",
            "service_name": "search-indexer",
            "title": "Queue processing delay",
            "severity": "critical",
            "status": "open",
            "recovery_status": "Not started",
            "error_rate": 5.4,
            "threshold": 2.0,
            "probable_cause": "Consumer lag increased after a retry storm.",
            "recommended_action": "Scale the consumer group after the queue backlog is inspected.",
            "evidence": [],
            "events": [],
        },
        {
            "id": "INC-2835",
            "service_id": "svc-api",
            "service_name": "checkout-api",
            "title": "Latency threshold exceeded",
            "severity": "medium",
            "status": "resolved",
            "recovery_status": "Verified",
            "error_rate": 0.46,
            "threshold": 0.8,
            "probable_cause": "Database connection pool saturation.",
            "recommended_action": "Connection pool limits were adjusted and health checks passed.",
            "evidence": [],
            "events": [],
        },
    ]

    for item in incidents_data:
        res = await session.execute(select(Incident).where(Incident.id == item["id"]))
        inc = res.scalar_one_or_none()
        if not inc:
            inc = Incident(
                id=item["id"],
                organization_id=org.id,
                service_id=item["service_id"],
                service_name=item["service_name"],
                title=item["title"],
                severity=item["severity"],
                status=item["status"],
                detected_at=datetime.now(timezone.utc),
                recovery_status=item["recovery_status"],
                error_rate=item["error_rate"],
                threshold=item["threshold"],
                probable_cause=item["probable_cause"],
                recommended_action=item["recommended_action"],
            )
            session.add(inc)

            for ev in item["evidence"]:
                session.add(IncidentEvidence(
                    id=ev["id"],
                    incident_id=inc.id,
                    kind=ev["kind"],
                    title=ev["title"],
                    detail=ev["detail"],
                    timestamp=datetime.now(timezone.utc),
                ))

            for event in item["events"]:
                session.add(IncidentEvent(
                    id=event["id"],
                    incident_id=inc.id,
                    label=event["label"],
                    detail=event["detail"],
                    tone=event["tone"],
                    timestamp=datetime.now(timezone.utc),
                ))
            logger.info("Seeded incident: %s (%s)", inc.id, inc.title)

    await session.flush()


async def seed_recoveries(session: AsyncSession) -> None:
    """Seeds baseline recovery queue actions and completed history."""
    recoveries_data = [
        {
            "id": "REC-611",
            "incident_id": "INC-2841",
            "service_id": "svc-web",
            "service_name": "customer-web",
            "action": "Rollback to previous stable release",
            "status": "pending_approval",
            "approval_required": True,
            "requested_by": "AutoHeal policy",
            "verification": "pending",
            "duration_seconds": None,
            "result": None,
        },
        {
            "id": "REC-609",
            "incident_id": "INC-2835",
            "service_id": "svc-api",
            "service_name": "checkout-api",
            "action": "Tune database connection pool",
            "status": "completed",
            "approval_required": True,
            "requested_by": "Morgan Lee",
            "verification": "passed",
            "duration_seconds": 42,
            "result": {"verified": True, "summary": "All configured health checks passed."},
        },
        {
            "id": "REC-602",
            "incident_id": "INC-2838",
            "service_id": "svc-search",
            "service_name": "search-indexer",
            "action": "Scale consumer group",
            "status": "failed",
            "approval_required": True,
            "requested_by": "Alex Chen",
            "verification": "failed",
            "duration_seconds": 13,
            "result": {"verified": False, "summary": "Policy precondition was not satisfied."},
        },
    ]

    for item in recoveries_data:
        res = await session.execute(select(RecoveryAction).where(RecoveryAction.id == item["id"]))
        rec = res.scalar_one_or_none()
        if not rec:
            rec = RecoveryAction(
                id=item["id"],
                incident_id=item["incident_id"],
                service_id=item["service_id"],
                service_name=item["service_name"],
                action=item["action"],
                status=item["status"],
                approval_required=item["approval_required"],
                requested_by=item["requested_by"],
                requested_at=datetime.now(timezone.utc),
                duration_seconds=item["duration_seconds"],
                verification=item["verification"],
            )
            session.add(rec)

            if item["result"]:
                session.add(RecoveryResult(
                    id=uuid.uuid4(),
                    recovery_action_id=rec.id,
                    verified=item["result"]["verified"],
                    summary=item["result"]["summary"],
                    completed_at=datetime.now(timezone.utc),
                ))
            logger.info("Seeded recovery action: %s (%s)", rec.id, rec.action)

    await session.flush()


async def run_seed() -> None:
    """Executes all seeder operations in an idempotent transaction."""
    logger.info("Starting AutoHeal database seed...")
    async with async_session_factory() as session:
        async with session.begin():
            org = await seed_organization(session)
            await seed_admin_user(session, org)
            await seed_services(session, org)
            await seed_incidents(session, org)
            await seed_recoveries(session)
        logger.info("Database seed completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_seed())
