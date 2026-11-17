"""
AutoHeal DevOps — Real-Time Server-Sent Events (SSE) Route
Streams live incident, recovery, and service health updates to authenticated clients.
"""

import logging
from typing import Any, Dict
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.deps import OrgDep, UserDep
from app.services.events import event_broadcaster
from app.services.ticket import sse_ticket_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["Real-Time Events"])


@router.post(
    "/ticket",
    summary="Issue single-use, short-lived SSE connection ticket",
    response_model=Dict[str, Any],
)
async def create_event_ticket(
    org: OrgDep,
    current_user: UserDep,
) -> Dict[str, Any]:
    """
    Issues a cryptographically secure, single-use ticket valid for 60 seconds.
    The frontend exchanges its Bearer token for this ticket before establishing an EventSource connection.
    Eliminates exposure of long-lived access tokens in URL query strings and proxy logs.
    """
    ticket, expires_in = sse_ticket_service.issue_ticket(
        user_id=str(current_user.id),
        org_id=str(org.id),
    )
    return {
        "ticket": ticket,
        "expires_in": expires_in,
        "token_type": "ticket",
    }


@router.get(
    "/stream",
    summary="Subscribe to organization real-time event stream (SSE)",
    response_class=StreamingResponse,
)
async def stream_events(
    request: Request,
    org: OrgDep,
    current_user: UserDep,
) -> StreamingResponse:
    """
    Establishes an authenticated Server-Sent Events (SSE) stream.
    Events are strictly scoped to the caller's organization.
    Supports JWT authentication via Bearer header or ?token=<token> query parameter.
    Emits periodic heartbeats every 15s to maintain active connection.
    """
    logger.info(f"[SSE] Establishing event stream for user {current_user.email} in org {org.slug} ({org.id})")

    return StreamingResponse(
        event_broadcaster.subscribe(org.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
