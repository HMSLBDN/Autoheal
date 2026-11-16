"""
AutoHeal DevOps — Real-Time Server-Sent Events (SSE) Route
Streams live incident, recovery, and service health updates to authenticated clients.
"""

import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.deps import OrgDep, UserDep
from app.services.events import event_broadcaster

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["Real-Time Events"])


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
