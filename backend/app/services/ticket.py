"""
AutoHeal DevOps — Single-Use SSE Ticket Service
Provides short-lived (60s), single-use cryptographically secure tickets for Server-Sent Events (SSE).
Prevents long-lived JWT access tokens from appearing in web server access logs or browser history.
"""

from datetime import datetime, timezone
import logging
import secrets
import time
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# In-memory ticket storage (supports Redis in distributed production)
_TICKET_STORE: Dict[str, Dict[str, any]] = {}
DEFAULT_TICKET_TTL_SECONDS = 60


def clean_expired_tickets() -> None:
    """Purges expired tickets from the memory cache."""
    now = time.time()
    expired = [k for k, v in _TICKET_STORE.items() if now > v.get("expires_at", 0)]
    for k in expired:
        _TICKET_STORE.pop(k, None)


class SSETicketService:
    """
    Manages generation, storage, and atomic single-use consumption of SSE tickets.
    """

    def __init__(self, ttl_seconds: int = DEFAULT_TICKET_TTL_SECONDS):
        self.ttl_seconds = ttl_seconds

    def issue_ticket(self, user_id: str, org_id: str) -> Tuple[str, int]:
        """
        Generates a 32-byte cryptographically secure random ticket valid for self.ttl_seconds.
        Returns: (ticket_string, expires_in_seconds)
        """
        clean_expired_tickets()
        ticket = secrets.token_urlsafe(32)
        now = time.time()

        _TICKET_STORE[ticket] = {
            "user_id": str(user_id),
            "org_id": str(org_id),
            "created_at": now,
            "expires_at": now + self.ttl_seconds,
        }

        logger.debug("Issued SSE ticket for user %s (valid %ss)", user_id, self.ttl_seconds)
        return ticket, self.ttl_seconds

    def consume_ticket(self, ticket: str) -> Optional[Dict[str, any]]:
        """
        Atomically validates and burns (single-use) the provided ticket.
        Returns ticket payload dict if valid, or None if invalid/expired/already used.
        """
        clean_expired_tickets()

        if not ticket or ticket not in _TICKET_STORE:
            logger.warning("SSE ticket consumption failed: Ticket not found or already consumed.")
            return None

        data = _TICKET_STORE.pop(ticket)
        now = time.time()

        if now > data.get("expires_at", 0):
            logger.warning("SSE ticket consumption failed: Ticket expired.")
            return None

        logger.debug("Successfully consumed single-use SSE ticket for user %s", data.get("user_id"))
        return data


sse_ticket_service = SSETicketService()
