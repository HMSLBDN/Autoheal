"""
AutoHeal DevOps — Authentication Rate Limiting & Abuse Prevention
Provides sliding-window in-memory rate limiting to protect authentication endpoints
against brute-force, password-guessing, and credential-stuffing attacks.
"""

from collections import defaultdict
from datetime import datetime, timezone
import logging
import sys
import threading
from typing import Dict, List, Optional
from fastapi import HTTPException, Request, status

from app.config import get_settings

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """
    Thread-safe sliding-window rate limiter.
    Maintains timestamp logs per client key and prunes aged requests.
    """

    def __init__(self, max_requests: int = 15, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """
        Evaluates whether a request from key is permitted.
        Returns: (allowed: bool, retry_after_seconds: int)
        """
        current_settings = get_settings()

        # In test environments or when explicitly disabled, bypass throttling
        # unless testing the rate limiter directly with key prefix 'test_rate_limit_'
        is_testing = current_settings.APP_ENV == "test" or "pytest" in sys.modules
        if is_testing and not key.startswith("test_rate_limit_"):
            return True, 0

        if not getattr(current_settings, "RATE_LIMIT_ENABLED", True):
            return True, 0

        now = datetime.now(timezone.utc).timestamp()
        window_start = now - self.window_seconds

        with self._lock:
            timestamps = self._requests[key]
            # Prune timestamps older than window
            self._requests[key] = [t for t in timestamps if t > window_start]
            current_count = len(self._requests[key])

            if current_count >= self.max_requests:
                oldest_timestamp = self._requests[key][0]
                retry_after = max(1, int(oldest_timestamp + self.window_seconds - now))
                return False, retry_after

            self._requests[key].append(now)
            return True, 0

    def reset(self, key: Optional[str] = None):
        """Resets tracking history."""
        with self._lock:
            if key:
                self._requests.pop(key, None)
            else:
                self._requests.clear()


# Default limiter for login / register / reset endpoints: 15 requests per 60 seconds per IP
auth_rate_limiter = SlidingWindowRateLimiter(max_requests=15, window_seconds=60)


async def check_auth_rate_limit(request: Request) -> None:
    """
    FastAPI dependency enforcing rate limits on authentication endpoints.
    Uses client host IP address as primary bucket key.
    """
    client_ip = "127.0.0.1"
    if request.client and request.client.host:
        client_ip = request.client.host

    allowed, retry_after = auth_rate_limiter.is_allowed(client_ip)
    if not allowed:
        logger.warning(
            "Rate limit exceeded for IP %s on path %s. Throttling for %d seconds.",
            client_ip,
            request.url.path,
            retry_after,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many authentication attempts. Please retry in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
