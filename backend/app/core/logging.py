"""
AutoHeal DevOps — Structured Application Logging & Observability
Provides JSON-structured logging, Request ID tracing, and sensitive credential masking.
"""

from collections import defaultdict
from datetime import datetime, timezone
import json
import logging
import threading
import time
from typing import Callable, Dict, Tuple
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


class TelemetryCollector:
    """
    In-memory Prometheus telemetry collector for runtime metrics.
    Tracks HTTP request counts, durations, and database pool status in a thread-safe manner.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.request_counts: Dict[Tuple[str, str, int], int] = defaultdict(int)
        self.request_duration_seconds: Dict[Tuple[str, str], float] = defaultdict(float)

    @staticmethod
    def _normalize_path(path: str) -> str:
        base = path.split("?")[0]
        segments = []
        for part in base.split("/"):
            if len(part) in (32, 36) and ("-" in part or part.isalnum()):
                segments.append(":id")
            elif part.isdigit():
                segments.append(":id")
            else:
                segments.append(part)
        return "/".join(segments) or "/"

    def record_request(self, method: str, path: str, status_code: int, duration_seconds: float) -> None:
        normalized_path = self._normalize_path(path)
        with self._lock:
            self.request_counts[(method, normalized_path, status_code)] += 1
            self.request_duration_seconds[(method, normalized_path)] += duration_seconds

    def generate_prometheus_metrics(
        self, pool_size: int = 0, pool_overflow: int = 0, pool_checkedout: int = 0
    ) -> str:
        lines = [
            "# HELP autoheal_api_up Service operational status gauge",
            "# TYPE autoheal_api_up gauge",
            "autoheal_api_up 1",
            "",
            "# HELP autoheal_database_pool_size Configured database connection pool size",
            "# TYPE autoheal_database_pool_size gauge",
            f"autoheal_database_pool_size {pool_size}",
            "",
            "# HELP autoheal_database_pool_overflow Active database connection pool overflow count",
            "# TYPE autoheal_database_pool_overflow gauge",
            f"autoheal_database_pool_overflow {pool_overflow}",
            "",
            "# HELP autoheal_database_pool_checkedout Number of database connections currently in use",
            "# TYPE autoheal_database_pool_checkedout gauge",
            f"autoheal_database_pool_checkedout {pool_checkedout}",
            "",
            "# HELP autoheal_http_requests_total Total HTTP requests processed by endpoint and status",
            "# TYPE autoheal_http_requests_total counter",
        ]

        with self._lock:
            for (method, endpoint, status_code), count in sorted(self.request_counts.items()):
                lines.append(
                    f'autoheal_http_requests_total{{method="{method}",endpoint="{endpoint}",status="{status_code}"}} {count}'
                )

            lines.append("")
            lines.append("# HELP autoheal_http_request_duration_seconds Cumulative request duration in seconds")
            lines.append("# TYPE autoheal_http_request_duration_seconds counter")
            for (method, endpoint), duration in sorted(self.request_duration_seconds.items()):
                lines.append(
                    f'autoheal_http_request_duration_seconds{{method="{method}",endpoint="{endpoint}"}} {duration:.6f}'
                )

        lines.append("")
        return "\n".join(lines)


telemetry = TelemetryCollector()


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
            duration_s = time.time() - start_time
            duration_ms = round(duration_s * 1000, 2)

            telemetry.record_request(request.method, request.url.path, response.status_code, duration_s)

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
            duration_s = time.time() - start_time
            duration_ms = round(duration_s * 1000, 2)
            telemetry.record_request(request.method, request.url.path, 500, duration_s)
            logger.error(
                "request_failed method=%s path=%s duration_ms=%s request_id=%s error=%s",
                request.method,
                request.url.path,
                duration_ms,
                request_id,
                str(exc),
            )
            raise exc
