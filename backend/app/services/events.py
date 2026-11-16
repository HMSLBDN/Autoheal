"""
AutoHeal DevOps — Real-Time Event Broadcaster
Manages per-organization event distribution and SSE streaming subscriptions.
Provides bounded queues, periodic heartbeats, and safe subscriber cleanup.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, AsyncGenerator, Dict, Optional, Set, Union
import uuid

logger = logging.getLogger(__name__)


class EventBroadcaster:
    """
    In-memory and Redis-capable event distributor for Server-Sent Events (SSE).
    Subscribers are strictly partitioned by organization ID to guarantee multi-tenant isolation.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, org_id: Union[str, uuid.UUID]) -> AsyncGenerator[str, None]:
        """
        Subscribes a client to SSE events for a specific organization.
        Yields standard text/event-stream chunks with heartbeats.
        """
        org_key = str(org_id)
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)

        async with self._lock:
            if org_key not in self._subscribers:
                self._subscribers[org_key] = set()
            self._subscribers[org_key].add(queue)

        logger.info(f"[SSE] Client subscribed to org {org_key} (active: {len(self._subscribers[org_key])})")

        try:
            # Send initial connected event
            init_data = json.dumps({
                "status": "connected",
                "organization_id": org_key,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            yield f"event: connected\ndata: {init_data}\n\n"

            while True:
                try:
                    # Wait for next event or 15-second heartbeat timeout
                    event_payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    event_type = event_payload.get("event", "message")
                    data = json.dumps(event_payload.get("data", {}))
                    yield f"event: {event_type}\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    # SSE keep-alive comment ensures reverse proxies and browsers do not drop the socket
                    yield ": keep-alive\n\n"
        except asyncio.CancelledError:
            logger.debug(f"[SSE] Subscription cancelled for org {org_key}")
            raise
        finally:
            async with self._lock:
                if org_key in self._subscribers:
                    self._subscribers[org_key].discard(queue)
                    if not self._subscribers[org_key]:
                        del self._subscribers[org_key]
            logger.info(f"[SSE] Client disconnected from org {org_key}")

    async def broadcast(
        self,
        org_id: Union[str, uuid.UUID],
        event_type: str,
        data: Any,
    ) -> int:
        """
        Delivers an event to all active SSE subscribers in the specified organization.
        Returns the number of subscribers reached.
        """
        org_key = str(org_id)
        message = {
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        async with self._lock:
            queues = list(self._subscribers.get(org_key, []))

        count = 0
        for q in queues:
            try:
                q.put_nowait(message)
                count += 1
            except asyncio.QueueFull:
                logger.warning(f"[SSE] Subscriber queue full for org {org_key}, dropping message")

        if count > 0:
            logger.debug(f"[SSE] Broadcast '{event_type}' to {count} clients in org {org_key}")
        return count


# Singleton broadcaster
event_broadcaster = EventBroadcaster()
