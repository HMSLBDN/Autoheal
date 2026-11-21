"""
AutoHeal DevOps — Enterprise Notification Center API Router
Manages notification channels (Email, Slack, Teams, Webhook), subscriptions, test dispatches,
and delivery history with exponential backoff retries.
"""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, and_, desc

from app.api.deps import DatabaseDep, OrgDep, RequireRole, UserDep
from app.models.enterprise import NotificationChannel, NotificationSubscription, NotificationDelivery
from app.schemas.enterprise import (
    NotificationChannelCreate,
    NotificationChannelResponse,
    NotificationChannelUpdate,
    NotificationDeliveryResponse,
    NotificationSubscriptionCreate,
    NotificationSubscriptionResponse,
    TestNotificationRequest,
    TestNotificationResponse,
)
from app.services.enterprise.dispatcher import NotificationDispatcher
from app.services.enterprise.adapters import get_adapter

router = APIRouter(prefix="/notifications", tags=["Notifications"])
dispatcher = NotificationDispatcher()


def mask_channel_config(config_str: str) -> Dict[str, Any]:
    """Masks secret tokens and sensitive URL parameters in channel configuration."""
    try:
        data = json.loads(config_str or "{}")
        masked = {}
        for k, v in data.items():
            if any(s in k.lower() for s in ["token", "secret", "password", "key"]):
                masked[k] = "********"
            elif "url" in k.lower() and isinstance(v, str):
                # Mask webhook tokens embedded in query strings or paths if lengthy
                masked[k] = v[:40] + "..." if len(v) > 40 else v
            else:
                masked[k] = v
        return masked
    except Exception:
        return {}


def serialize_channel(c: NotificationChannel) -> NotificationChannelResponse:
    return NotificationChannelResponse(
        id=str(c.id),
        organization_id=str(c.organization_id),
        name=c.name,
        channel_type=c.channel_type,
        is_enabled=c.is_enabled,
        config_masked=mask_channel_config(c.config_json),
        rate_limit_per_minute=c.rate_limit_per_minute,
        created_at=c.created_at.isoformat() if c.created_at else "",
        updated_at=c.updated_at.isoformat() if c.updated_at else "",
    )


def serialize_delivery(d: NotificationDelivery) -> NotificationDeliveryResponse:
    channel_name = d.channel.name if d.channel else "Unknown Channel"
    channel_type = d.channel.channel_type if d.channel else "webhook"
    return NotificationDeliveryResponse(
        id=str(d.id),
        organization_id=str(d.organization_id),
        channel_id=str(d.channel_id),
        channel_name=channel_name,
        channel_type=channel_type,
        incident_id=d.incident_id,
        event_type=d.event_type,
        idempotency_key=d.idempotency_key,
        payload=json.loads(d.payload_json or "{}"),
        status=d.status,
        retry_count=d.retry_count,
        max_retries=d.max_retries,
        provider_response_code=d.provider_response_code,
        failure_reason=d.failure_reason,
        delivered_at=d.delivered_at.isoformat() if d.delivered_at else None,
        next_retry_at=d.next_retry_at.isoformat() if d.next_retry_at else None,
        created_at=d.created_at.isoformat() if d.created_at else "",
    )


# ------------------------------------------------------------------------------
# Notification Channels
# ------------------------------------------------------------------------------

@router.get("/channels", response_model=List[NotificationChannelResponse], summary="List configured notification channels")
async def list_channels(
    org: OrgDep,
    db: DatabaseDep,
) -> List[NotificationChannelResponse]:
    """Lists notification channels scoped strictly to the organization with credentials masked."""
    q = select(NotificationChannel).where(
        NotificationChannel.organization_id == org.id
    ).order_by(desc(NotificationChannel.created_at))
    res = await db.execute(q)
    return [serialize_channel(c) for c in res.scalars().all()]


@router.post("/channels", response_model=NotificationChannelResponse, summary="Configure new notification channel", status_code=status.HTTP_201_CREATED)
async def create_channel(
    payload: NotificationChannelCreate,
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
) -> NotificationChannelResponse:
    """Configures a notification channel. Requires operator or admin role."""
    if user.role not in ["operator", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied. Operator or Admin role required.")

    channel = NotificationChannel(
        organization_id=org.id,
        name=payload.name,
        channel_type=payload.channel_type,
        is_enabled=payload.is_enabled,  # Defaults to False
        config_json=json.dumps(payload.config),
        secret_token=payload.secret_token,
        rate_limit_per_minute=payload.rate_limit_per_minute,
    )
    db.add(channel)
    await db.flush()
    return serialize_channel(channel)


@router.patch("/channels/{channel_id}", response_model=NotificationChannelResponse, summary="Update notification channel")
async def update_channel(
    channel_id: str,
    payload: NotificationChannelUpdate,
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
) -> NotificationChannelResponse:
    """Updates channel settings or toggles enabled state. Requires operator or admin role."""
    if user.role not in ["operator", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")

    try:
        cid = uuid.UUID(channel_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid channel ID.")

    q = select(NotificationChannel).where(
        and_(
            NotificationChannel.organization_id == org.id,
            NotificationChannel.id == cid,
        )
    )
    res = await db.execute(q)
    channel = res.scalars().first()
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification channel not found.")

    if payload.name is not None:
        channel.name = payload.name
    if payload.is_enabled is not None:
        channel.is_enabled = payload.is_enabled
    if payload.config is not None:
        channel.config_json = json.dumps(payload.config)
    if payload.secret_token is not None:
        channel.secret_token = payload.secret_token
    if payload.rate_limit_per_minute is not None:
        channel.rate_limit_per_minute = payload.rate_limit_per_minute

    await db.flush()
    return serialize_channel(channel)


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete notification channel")
async def delete_channel(
    channel_id: str,
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
):
    """Deletes notification channel. Requires admin role."""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required to delete notification channels.")

    try:
        cid = uuid.UUID(channel_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid channel ID.")

    q = select(NotificationChannel).where(
        and_(
            NotificationChannel.organization_id == org.id,
            NotificationChannel.id == cid,
        )
    )
    res = await db.execute(q)
    channel = res.scalars().first()
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification channel not found.")

    await db.delete(channel)
    await db.flush()


@router.post("/channels/{channel_id}/test", response_model=TestNotificationResponse, summary="Send test notification")
async def test_channel(
    channel_id: str,
    payload: TestNotificationRequest,
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
) -> TestNotificationResponse:
    """Dispatches a test notification to verify integration configuration."""
    try:
        cid = uuid.UUID(channel_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid channel ID.")

    q = select(NotificationChannel).where(
        and_(
            NotificationChannel.organization_id == org.id,
            NotificationChannel.id == cid,
        )
    )
    res = await db.execute(q)
    channel = res.scalars().first()
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification channel not found.")

    adapter = get_adapter(channel.channel_type)
    config = json.loads(channel.config_json or "{}")

    test_payload = {
        "organization": org.name,
        "event_type": "test_notification",
        "title": "AutoHeal Integration Health Check",
        "service_name": "autoheal-platform",
        "severity": "informational",
        "status": "verified",
        "incident_id": "TEST-PING",
        "evidence_summary": payload.message or "Verified integration health check",
        "recommended_action": "None required",
    }

    deliv_id = str(uuid.uuid4())
    success, code, err = await adapter.send(
        config=config,
        payload=test_payload,
        secret_token=channel.secret_token,
        delivery_id=deliv_id,
        timeout_seconds=5.0,
    )

    if success:
        return TestNotificationResponse(
            delivery_id=deliv_id,
            status="delivered",
            detail=f"Test notification verified successfully (HTTP {code}).",
        )
    else:
        return TestNotificationResponse(
            delivery_id=deliv_id,
            status="failed",
            detail=f"Test delivery failed (HTTP {code}): {err}",
        )


# ------------------------------------------------------------------------------
# Subscriptions
# ------------------------------------------------------------------------------

@router.get("/subscriptions", response_model=List[NotificationSubscriptionResponse], summary="List event subscriptions")
async def list_subscriptions(
    org: OrgDep,
    db: DatabaseDep,
) -> List[NotificationSubscriptionResponse]:
    """Lists event subscriptions for the organization."""
    q = select(NotificationSubscription).where(
        NotificationSubscription.organization_id == org.id
    ).order_by(desc(NotificationSubscription.created_at))
    res = await db.execute(q)
    subs = res.scalars().all()
    return [
        NotificationSubscriptionResponse(
            id=str(s.id),
            organization_id=str(s.organization_id),
            channel_id=str(s.channel_id),
            event_type=s.event_type,
            min_severity=s.min_severity,
            is_active=s.is_active,
            created_at=s.created_at.isoformat(),
        )
        for s in subs
    ]


@router.post("/subscriptions", response_model=NotificationSubscriptionResponse, summary="Subscribe channel to event trigger", status_code=status.HTTP_201_CREATED)
async def create_subscription(
    payload: NotificationSubscriptionCreate,
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
) -> NotificationSubscriptionResponse:
    """Subscribes a channel to specific incident or recovery events."""
    try:
        cid = uuid.UUID(payload.channel_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid channel ID.")

    sub = NotificationSubscription(
        organization_id=org.id,
        channel_id=cid,
        event_type=payload.event_type,
        min_severity=payload.min_severity,
        is_active=payload.is_active,
    )
    db.add(sub)
    await db.flush()

    return NotificationSubscriptionResponse(
        id=str(sub.id),
        organization_id=str(sub.organization_id),
        channel_id=str(sub.channel_id),
        event_type=sub.event_type,
        min_severity=sub.min_severity,
        is_active=sub.is_active,
        created_at=sub.created_at.isoformat(),
    )


# ------------------------------------------------------------------------------
# Delivery History & Retries
# ------------------------------------------------------------------------------

@router.get("/deliveries", response_model=List[NotificationDeliveryResponse], summary="List notification delivery history")
async def list_deliveries(
    org: OrgDep,
    db: DatabaseDep,
    channel_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(default=50, le=200),
) -> List[NotificationDeliveryResponse]:
    """Lists delivery attempts, delivery statuses, response codes, and timestamps."""
    q = select(NotificationDelivery).where(NotificationDelivery.organization_id == org.id)
    if channel_id:
        try:
            q = q.where(NotificationDelivery.channel_id == uuid.UUID(channel_id))
        except ValueError:
            pass
    if status_filter:
        q = q.where(NotificationDelivery.status == status_filter)

    q = q.order_by(desc(NotificationDelivery.created_at)).limit(limit)
    res = await db.execute(q)
    return [serialize_delivery(d) for d in res.scalars().all()]


@router.post("/deliveries/{delivery_id}/retry", response_model=NotificationDeliveryResponse, summary="Retry failed delivery")
async def retry_delivery(
    delivery_id: str,
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
) -> NotificationDeliveryResponse:
    """Retries an eligible failed notification delivery."""
    try:
        did = uuid.UUID(delivery_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid delivery ID.")

    delivery = await dispatcher.retry_delivery(
        db=db,
        organization_id=org.id,
        delivery_id=did,
    )
    if not delivery:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery record not found.")

    return serialize_delivery(delivery)
