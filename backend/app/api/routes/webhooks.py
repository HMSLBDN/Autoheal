"""
AutoHeal DevOps — Enterprise Webhooks API Router
Configures and manages outbound signed webhooks with SSRF prevention and HMAC verification.
"""

from datetime import datetime
import json
import secrets
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, desc

from app.api.deps import DatabaseDep, OrgDep, RequireRole, UserDep
from app.models.enterprise import WebhookEndpoint, WebhookDeliveryAttempt
from app.schemas.enterprise import (
    WebhookEndpointCreate,
    WebhookEndpointResponse,
    WebhookEndpointUpdate,
    WebhookDeliveryAttemptResponse,
)
from app.services.enterprise.ssrf import is_ssrf_safe_url
from app.services.enterprise.adapters import verify_hmac_signature

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class WebhookVerifyRequest(BaseModel):
    secret: str
    signature: str
    timestamp: str
    payload: Dict[str, Any]
    max_skew_seconds: int = Field(300, ge=30, le=3600)


class WebhookVerifyResponse(BaseModel):
    is_valid: bool
    detail: str


def serialize_webhook(ep: WebhookEndpoint) -> WebhookEndpointResponse:
    try:
        events = json.loads(ep.events_json or "[]")
    except Exception:
        events = ["*"]

    return WebhookEndpointResponse(
        id=str(ep.id),
        organization_id=str(ep.organization_id),
        name=ep.name,
        target_url=ep.target_url,
        is_active=ep.is_active,
        events=events,
        timeout_seconds=ep.timeout_seconds,
        created_at=ep.created_at.isoformat() if ep.created_at else "",
        updated_at=ep.updated_at.isoformat() if ep.updated_at else "",
    )


def serialize_attempt(att: WebhookDeliveryAttempt) -> WebhookDeliveryAttemptResponse:
    try:
        payload = json.loads(att.payload_json or "{}")
    except Exception:
        payload = {}

    return WebhookDeliveryAttemptResponse(
        id=str(att.id),
        delivery_id=att.delivery_id,
        event_type=att.event_type,
        payload=payload,
        signature_header=att.signature_header,
        response_status_code=att.response_status_code,
        status=att.status,
        error_message=att.error_message,
        duration_ms=att.duration_ms,
        created_at=att.created_at.isoformat() if att.created_at else "",
    )


@router.get("/endpoints", response_model=List[WebhookEndpointResponse], summary="List outbound webhook endpoints")
async def list_endpoints(
    org: OrgDep,
    db: DatabaseDep,
) -> List[WebhookEndpointResponse]:
    """Lists registered outbound webhook endpoints (signing secrets masked/omitted)."""
    q = select(WebhookEndpoint).where(
        WebhookEndpoint.organization_id == org.id
    ).order_by(desc(WebhookEndpoint.created_at))
    res = await db.execute(q)
    return [serialize_webhook(ep) for ep in res.scalars().all()]


@router.post("/endpoints", response_model=WebhookEndpointResponse, summary="Register outbound webhook endpoint", status_code=status.HTTP_201_CREATED)
async def create_endpoint(
    payload: WebhookEndpointCreate,
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
) -> WebhookEndpointResponse:
    """Registers an outbound webhook endpoint. Strictly performs SSRF checks on target_url."""
    if user.role not in ["operator", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operator or Admin role required.")

    # SSRF verification: reject private networks, localhost, link-local, cloud metadata
    is_safe, reason = is_ssrf_safe_url(payload.target_url, allow_local_for_testing=False)
    if not is_safe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Webhook target URL rejected due to security policy: {reason}",
        )

    signing_secret = payload.secret_token or secrets.token_hex(24)
    endpoint = WebhookEndpoint(
        organization_id=org.id,
        name=payload.name,
        target_url=payload.target_url,
        secret_token=signing_secret,
        is_active=payload.is_active,  # False by default
        events_json=json.dumps(payload.events),
        timeout_seconds=payload.timeout_seconds,
    )
    db.add(endpoint)
    await db.flush()
    return serialize_webhook(endpoint)


@router.get("/endpoints/{endpoint_id}", response_model=WebhookEndpointResponse, summary="Get webhook endpoint details")
async def get_endpoint(
    endpoint_id: str,
    org: OrgDep,
    db: DatabaseDep,
) -> WebhookEndpointResponse:
    """Retrieves endpoint configuration."""
    try:
        eid = uuid.UUID(endpoint_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid endpoint ID.")

    q = select(WebhookEndpoint).where(
        and_(
            WebhookEndpoint.organization_id == org.id,
            WebhookEndpoint.id == eid,
        )
    )
    res = await db.execute(q)
    endpoint = res.scalars().first()
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found.")

    return serialize_webhook(endpoint)


@router.patch("/endpoints/{endpoint_id}", response_model=WebhookEndpointResponse, summary="Update webhook endpoint")
async def update_endpoint(
    endpoint_id: str,
    payload: WebhookEndpointUpdate,
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
) -> WebhookEndpointResponse:
    """Updates webhook configuration. Validates SSRF safety if target_url is modified."""
    if user.role not in ["operator", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operator or Admin role required.")

    try:
        eid = uuid.UUID(endpoint_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid endpoint ID.")

    q = select(WebhookEndpoint).where(
        and_(
            WebhookEndpoint.organization_id == org.id,
            WebhookEndpoint.id == eid,
        )
    )
    res = await db.execute(q)
    endpoint = res.scalars().first()
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found.")

    if payload.target_url is not None:
        is_safe, reason = is_ssrf_safe_url(payload.target_url, allow_local_for_testing=False)
        if not is_safe:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Webhook target URL rejected due to security policy: {reason}",
            )
        endpoint.target_url = payload.target_url

    if payload.name is not None:
        endpoint.name = payload.name
    if payload.secret_token is not None:
        endpoint.secret_token = payload.secret_token
    if payload.is_active is not None:
        endpoint.is_active = payload.is_active
    if payload.events is not None:
        endpoint.events_json = json.dumps(payload.events)
    if payload.timeout_seconds is not None:
        endpoint.timeout_seconds = payload.timeout_seconds

    await db.flush()
    return serialize_webhook(endpoint)


@router.delete("/endpoints/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete webhook endpoint")
async def delete_endpoint(
    endpoint_id: str,
    org: OrgDep,
    user: UserDep,
    db: DatabaseDep,
):
    """Deletes webhook endpoint. Admin role required."""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required to delete webhook endpoints.")

    try:
        eid = uuid.UUID(endpoint_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid endpoint ID.")

    q = select(WebhookEndpoint).where(
        and_(
            WebhookEndpoint.organization_id == org.id,
            WebhookEndpoint.id == eid,
        )
    )
    res = await db.execute(q)
    endpoint = res.scalars().first()
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found.")

    await db.delete(endpoint)
    await db.flush()


@router.get("/endpoints/{endpoint_id}/deliveries", response_model=List[WebhookDeliveryAttemptResponse], summary="List webhook deliveries")
async def list_endpoint_deliveries(
    endpoint_id: str,
    org: OrgDep,
    db: DatabaseDep,
    limit: int = Query(default=50, le=200),
) -> List[WebhookDeliveryAttemptResponse]:
    """Retrieves delivery audit history for a specific endpoint."""
    try:
        eid = uuid.UUID(endpoint_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid endpoint ID.")

    q = (
        select(WebhookDeliveryAttempt)
        .where(
            and_(
                WebhookDeliveryAttempt.organization_id == org.id,
                WebhookDeliveryAttempt.endpoint_id == eid,
            )
        )
        .order_by(desc(WebhookDeliveryAttempt.created_at))
        .limit(limit)
    )
    res = await db.execute(q)
    return [serialize_attempt(att) for att in res.scalars().all()]


@router.post("/verify", response_model=WebhookVerifyResponse, summary="Validate webhook HMAC signature")
async def verify_signature_endpoint(
    req: WebhookVerifyRequest,
) -> WebhookVerifyResponse:
    """Utility endpoint to verify HMAC-SHA256 signatures and timestamp freshness."""
    raw_payload = json.dumps(req.payload, sort_keys=True).encode("utf-8")
    is_valid, msg = verify_hmac_signature(
        secret=req.secret,
        signature=req.signature,
        timestamp=req.timestamp,
        payload_bytes=raw_payload,
        max_skew_seconds=req.max_skew_seconds,
    )
    return WebhookVerifyResponse(is_valid=is_valid, detail=msg)
