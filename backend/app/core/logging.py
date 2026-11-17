"""
AutoHeal DevOps — Structured Application Logging & Observability
Provides JSON-structured logging, Request ID tracing, and sensitive credential masking.
"""

from datetime import datetime, timezone
import json
import logging
import time
from typing import Callable
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("autoheal.access")

SENSITIVE_KEYS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "authorization",
    "secret_key",
}


def mask_sensitive_data(data: dict) -> dict:
    """Recursively masks sensitive values in dictionaries."""
    sanitized = {}
    for k, v in data.items():
        if any(sens in k.lower() for sens in SENSITIVE_KEYS):
            sanitized[k] = "******"
        elif isinstance(v, dict):
            sanitized[k] = mask_sensitive_data(v)
        elif isinstance(v, list):
            sanitized[k] = [mask_sensitive_data(i) if isinstance(i, dict) else i for i in v]
        else:
            sanitized[k] = v
    return sanitized


class RequestTracingMiddleware(BaseHTTPMiddleware):
    """
    Attaches a unique X-Request-ID correlation header to every HTTP request.
    Records structured access logs with latency metrics, omitting sensitive credentials.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or f"req-{uuid.uuid4().hex[:12]}"
        request.state.request_id = request_id

        start_time = time.time()
        try:
            response = await call_next(request)
            duration_ms = round((time.time() - start_time) * 1000, 2)

            response.headers["X-Request-ID"] = request_id

            # Avoid logging health checks at high volume
            if not request.url.path.endswith("/health"):
                logger.info(
                    "request_completed method=%s path=%s status=%s duration_ms=%s request_id=%s",
                    request.method,
                    request.url.path,
                    response.status_code,
                    duration_ms,
                    request_id,
                )
            return response
        except Exception as exc:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            logger.error(
                "request_failed method=%s path=%s duration_ms=%s request_id=%s error=%s",
                request.method,
                request.url.path,
                duration_ms,
                request_id,
                str(exc),
            )
            raise exc
