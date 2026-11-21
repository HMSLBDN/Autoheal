"""
AutoHeal DevOps — Enterprise Notification Dispatcher & Delivery Engine
Evaluates event subscriptions, enforces per-tenant rate limits, generates idempotency keys,
and coordinates dispatch across Email, Slack, Teams, and generic Webhook adapters.
Failures in delivery never disrupt incident creation or recovery workflows.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enterprise import NotificationChannel, NotificationSubscription, NotificationDelivery
from app.models.organization import Organization
from app.models.base import utc_now
from app.services.enterprise.adapters import get_adapter

logger = logging.getLogger(__name__)


def generate_idempotency_key(
    organization_id: uuid.UUID,
    channel_id: uuid.UUID,
    event_type: str,
    incident_id: Optional[str] = None,
    window_minutes: int = 5,
) -> str:
    """
    Constructs an idempotency key scoped to a time window to prevent notification spam
    and duplicate deliveries.
    """
    now = datetime.now(timezone.utc)
    # Bucket timestamps into 5-minute windows
    bucket = now.strftime("%Y-%m-%d-%H-") + str(now.minute // window_minutes)
    raw = f"{organization_id}:{channel_id}:{event_type}:{incident_id or 'none'}:{bucket}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def build_sanitized_notification_payload(
    org_name: str,
    event_type: str,
    title: str,
    service_name: str,
    severity: str,
    status: str,
    incident_id: Optional[str] = None,
    short_evidence: Optional[str] = None,
    recommended_action: Optional[str] = None,
    dashboard_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Constructs a minimal, secure notification payload without exposing internal secrets or sensitive logs.
    """
    return {
        "organization": org_name,
        "event_type": event_type,
        "incident_id": incident_id or "N/A",
        "title": title[:200],
        "service_name": service_name[:100],
        "severity": severity.lower(),
        "status": status.lower(),
        "detected_at": utc_now().isoformat(),
        "evidence_summary": (short_evidence or "Telemetry anomaly detected")[:300],
        "recommended_action": (recommended_action or "Review operational dashboard")[:200],
        "dashboard_link": dashboard_url or f"/dashboard/incidents/{incident_id or ''}",
    }


class NotificationDispatcher:
    """
    Coordinates channel routing, subscription matching, rate limiting, and reliable delivery.
    """

    async def dispatch_event(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        event_type: str,
        title: str,
        service_name: str,
        severity: str = "medium",
        status: str = "open",
        incident_id: Optional[str] = None,
        short_evidence: Optional[str] = None,
        recommended_action: Optional[str] = None,
    ) -> List[NotificationDelivery]:
        """
        Dispatches notification across all active channels subscribed to this event_type.
        """
        try:
            # 1. Fetch organization name
            org_res = await db.execute(select(Organization).where(Organization.id == organization_id))
            org = org_res.scalars().first()
            org_name = org.name if org else "Default Org"

            payload = build_sanitized_notification_payload(
                org_name=org_name,
                event_type=event_type,
                title=title,
                service_name=service_name,
                severity=severity,
                status=status,
                incident_id=incident_id,
                short_evidence=short_evidence,
                recommended_action=recommended_action,
            )

            # 2. Query active subscriptions matching event_type (or wildcard "*")
            sub_q = (
                select(NotificationSubscription, NotificationChannel)
                .join(NotificationChannel, NotificationChannel.id == NotificationSubscription.channel_id)
                .where(
                    and_(
                        NotificationSubscription.organization_id == organization_id,
                        NotificationSubscription.is_active == True,
                        (
                            (NotificationSubscription.event_type == event_type)
                            | (NotificationSubscription.event_type == "*")
                        ),
                    )
                )
            )
            sub_res = await db.execute(sub_q)
            rows = sub_res.all()

            if not rows:
                # Fallback: if no explicit subscription rules configured, dispatch to all enabled channels
                chan_q = select(NotificationChannel).where(
                    and_(
                        NotificationChannel.organization_id == organization_id,
                        NotificationChannel.is_enabled == True,
                    )
                )
                chan_res = await db.execute(chan_q)
                rows = [(None, ch) for ch in chan_res.scalars().all()]

            deliveries: List[NotificationDelivery] = []

            for sub, channel in rows:
                if not channel.is_enabled:
                    # Mandatory rule: Channel disabled by default until explicitly enabled
                    continue

                idempotency_key = generate_idempotency_key(
                    organization_id=organization_id,
                    channel_id=channel.id,
                    event_type=event_type,
                    incident_id=incident_id,
                )

                # Check for existing delivery with this idempotency key
                dup_q = select(NotificationDelivery).where(
                    and_(
                        NotificationDelivery.organization_id == organization_id,
                        NotificationDelivery.idempotency_key == idempotency_key,
                    )
                )
                dup_res = await db.execute(dup_q)
                existing_dup = dup_res.scalars().first()
                if existing_dup:
                    # Duplicate delivery suppressed, return existing record
                    deliveries.append(existing_dup)
                    continue

                # Rate limiting check: verify deliveries in last 60 seconds
                one_min_ago = utc_now() - timedelta(minutes=1)
                rate_q = select(func.count(NotificationDelivery.id)).where(
                    and_(
                        NotificationDelivery.channel_id == channel.id,
                        NotificationDelivery.created_at >= one_min_ago,
                    )
                )
                rate_count = (await db.execute(rate_q)).scalar() or 0
                if rate_count >= channel.rate_limit_per_minute:
                    logger.warning(
                        "Notification rate limit reached for channel %s (%d msgs/min)",
                        channel.name,
                        channel.rate_limit_per_minute,
                    )
                    continue

                # Create Delivery record
                delivery = NotificationDelivery(
                    organization_id=organization_id,
                    channel_id=channel.id,
                    incident_id=incident_id,
                    event_type=event_type,
                    idempotency_key=idempotency_key,
                    payload_json=json.dumps(payload),
                    status="processing",
                    retry_count=0,
                    max_retries=3,
                    created_at=utc_now(),
                )
                db.add(delivery)
                await db.flush()

                # Dispatch via adapter
                adapter = get_adapter(channel.channel_type)
                config = json.loads(channel.config_json or "{}")

                success, code, err = await adapter.send(
                    config=config,
                    payload=payload,
                    secret_token=channel.secret_token,
                    delivery_id=str(delivery.id),
                    timeout_seconds=10.0,
                )

                delivery.provider_response_code = code
                if success:
                    delivery.status = "delivered"
                    delivery.delivered_at = utc_now()
                else:
                    delivery.status = "failed"
                    delivery.failure_reason = err
                    delivery.next_retry_at = utc_now() + timedelta(seconds=10)

                await db.flush()
                deliveries.append(delivery)

            return deliveries

        except Exception as e:
            # Non-blocking invariant: Notification failures must never interrupt caller
            logger.error("Failed to dispatch notifications for event '%s': %s", event_type, e)
            return []

    async def retry_delivery(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        delivery_id: uuid.UUID,
    ) -> Optional[NotificationDelivery]:
        """
        Retries a failed delivery record with exponential backoff calculation.
        """
        deliv_q = (
            select(NotificationDelivery, NotificationChannel)
            .join(NotificationChannel, NotificationChannel.id == NotificationDelivery.channel_id)
            .where(
                and_(
                    NotificationDelivery.organization_id == organization_id,
                    NotificationDelivery.id == delivery_id,
                )
            )
        )
        res = await db.execute(deliv_q)
        row = res.first()
        if not row:
            return None

        delivery, channel = row
        if delivery.status not in ["failed", "retrying"]:
            return delivery

        if delivery.retry_count >= delivery.max_retries:
            delivery.status = "permanently_failed"
            await db.flush()
            return delivery

        delivery.retry_count += 1
        delivery.status = "retrying"

        # Dispatch retry
        adapter = get_adapter(channel.channel_type)
        config = json.loads(channel.config_json or "{}")
        payload = json.loads(delivery.payload_json)

        success, code, err = await adapter.send(
            config=config,
            payload=payload,
            secret_token=channel.secret_token,
            delivery_id=str(delivery.id),
        )

        delivery.provider_response_code = code
        if success:
            delivery.status = "delivered"
            delivery.delivered_at = utc_now()
            delivery.failure_reason = None
        else:
            if delivery.retry_count >= delivery.max_retries:
                delivery.status = "permanently_failed"
            else:
                delivery.status = "failed"
            delivery.failure_reason = err
            # Exponential backoff: 5s * 2^(retry_count)
            backoff_sec = 5 * (2 ** delivery.retry_count)
            delivery.next_retry_at = utc_now() + timedelta(seconds=backoff_sec)

        await db.flush()
        return delivery
