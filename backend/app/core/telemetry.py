"""
AutoHeal DevOps — OpenTelemetry Distributed Tracing & Sensitive Data Redaction
Provides W3C TraceContext propagation, OpenTelemetry spans with automatic
credential scrubbing, and an in-memory trace buffer for observability dashboards.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import os
import re
import threading
import time
from typing import Optional, Dict, Any, Generator, List
import uuid

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger("autoheal.telemetry")

# Initialize OpenTelemetry Tracer
tracer = trace.get_tracer("autoheal.backend", "1.0.0")

# Keys and patterns requiring redaction from distributed traces
SENSITIVE_ATTR_PATTERNS = [
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"auth(orization)?", re.IGNORECASE),
    re.compile(r"cookie", re.IGNORECASE),
    re.compile(r"key", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
]

_BEARER_REGEX = re.compile(r"Bearer\s+[A-Za-z0-9\-_.]+", re.IGNORECASE)


def redact_sensitive_value(key: str, value: Any) -> Any:
    """
    Sanitizes trace attributes to prevent leaking credentials into telemetry backends.
    """
    if any(pat.search(key) for pat in SENSITIVE_ATTR_PATTERNS):
        return "[REDACTED]"

    if isinstance(value, str):
        if _BEARER_REGEX.search(value):
            return _BEARER_REGEX.sub("Bearer [REDACTED]", value)
        if len(value) > 500:
            return value[:500] + "...[TRUNCATED]"
        return value
    elif isinstance(value, dict):
        return {k: redact_sensitive_value(k, v) for k, v in value.items()}
    elif isinstance(value, (list, tuple)):
        return [redact_sensitive_value(key, item) for item in value]
    return value


class TraceRecord:
    """Represents a lightweight completed span record for the observability UI."""
    def __init__(
        self,
        trace_id: str,
        span_id: str,
        name: str,
        service: str,
        duration_ms: float,
        status: str,
        attributes: Dict[str, Any],
        timestamp: datetime,
    ):
        self.trace_id = trace_id
        self.span_id = span_id
        self.name = name
        self.service = service
        self.duration_ms = duration_ms
        self.status = status
        self.attributes = attributes
        self.timestamp = timestamp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "name": self.name,
            "service": self.service,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "attributes": self.attributes,
            "timestamp": self.timestamp.isoformat(),
        }


class InvertedTraceBuffer:
    """Thread-safe circular buffer storing recent distributed traces for dashboard viewing."""
    def __init__(self, capacity: int = 500):
        self.capacity = capacity
        self.traces: List[TraceRecord] = []
        self._lock = threading.Lock()

    def add(self, record: TraceRecord) -> None:
        with self._lock:
            self.traces.append(record)
            if len(self.traces) > self.capacity:
                self.traces.pop(0)

    def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return [t.to_dict() for t in reversed(self.traces[-limit:])]


trace_buffer = InvertedTraceBuffer()


@contextmanager
def trace_span(
    name: str,
    service: str = "autoheal-api",
    attributes: Optional[Dict[str, Any]] = None,
) -> Generator[trace.Span, None, None]:
    """
    Context manager that starts an OpenTelemetry span, redacting all sensitive attributes,
    records execution latency, status, and adds trace info to the in-memory buffer.
    """
    sanitized_attrs: Dict[str, Any] = {}
    if attributes:
        for k, v in attributes.items():
            sanitized_attrs[k] = redact_sensitive_value(k, v)

    sanitized_attrs["service.name"] = service

    start_time = time.time()
    start_dt = datetime.now(timezone.utc)
    status_str = "OK"

    with tracer.start_as_current_span(name, attributes=sanitized_attrs) as span:
        ctx = span.get_span_context()
        trace_id = f"{ctx.trace_id:032x}" if ctx.trace_id else uuid.uuid4().hex
        span_id = f"{ctx.span_id:016x}" if ctx.span_id else uuid.uuid4().hex[:16]

        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            status_str = "ERROR"
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise
        finally:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            record = TraceRecord(
                trace_id=trace_id,
                span_id=span_id,
                name=name,
                service=service,
                duration_ms=duration_ms,
                status=status_str,
                attributes=sanitized_attrs,
                timestamp=start_dt,
            )
            trace_buffer.add(record)
