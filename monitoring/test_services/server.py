"""
AutoHeal DevOps — Realistic Test Microservice
Simulates microservice telemetry, configurable chaos scenarios,
Prometheus metrics exposition, and health checks.
"""

import http.server
import json
import logging
import os
import random
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict

# Configure structured JSON logging
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_fields"):
            log_obj.update(record.extra_fields)
        return json.dumps(log_obj)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logger = logging.getLogger("test_service")
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False

SERVICE_NAME = os.environ.get("SERVICE_NAME", "checkout-api")
SERVICE_PORT = int(os.environ.get("SERVICE_PORT", "8080"))
SERVICE_ENV = os.environ.get("SERVICE_ENV", "production")

# Global mutable service state protected by a lock
class ServiceState:
    def __init__(self):
        self.lock = threading.Lock()
        self.status = "healthy"  # healthy, degraded, unhealthy
        self.latency_ms = 25
        self.error_rate = 0.00   # 0.0 to 1.0
        self.cpu_usage = 0.22    # 0.0 to 1.0
        self.memory_bytes = 268435456  # 256MB
        self.total_requests = 100
        self.total_errors = 0
        self.start_time = time.time()

    def get_state(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "service": SERVICE_NAME,
                "environment": SERVICE_ENV,
                "status": self.status,
                "latency_ms": self.latency_ms,
                "error_rate": self.error_rate,
                "cpu_usage": self.cpu_usage,
                "memory_bytes": self.memory_bytes,
                "total_requests": self.total_requests,
                "total_errors": self.total_errors,
                "uptime_seconds": int(time.time() - self.start_time),
            }

    def record_request(self, is_error: bool):
        with self.lock:
            self.total_requests += 1
            if is_error:
                self.total_errors += 1

    def set_chaos(self, status: str = None, latency_ms: int = None, error_rate: float = None, cpu_usage: float = None, memory_bytes: int = None):
        with self.lock:
            if status is not None:
                self.status = status
            if latency_ms is not None:
                self.latency_ms = latency_ms
            if error_rate is not None:
                self.error_rate = error_rate
            if cpu_usage is not None:
                self.cpu_usage = cpu_usage
            if memory_bytes is not None:
                self.memory_bytes = memory_bytes

    def reset_health(self):
        with self.lock:
            self.status = "healthy"
            self.latency_ms = 20
            self.error_rate = 0.0
            self.cpu_usage = 0.20
            self.memory_bytes = 268435456

state = ServiceState()


class TestServiceRequestHandler(http.server.BaseHTTPRequestHandler):
    """Handles HTTP requests for health probing, metrics, and chaos injection."""

    def log_message(self, format, *args):
        # Suppress default stdlib stderr logging in favor of structured logger
        pass

    def _send_json(self, status_code: int, data: Dict[str, Any]):
        response_bytes = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def _send_text(self, status_code: int, text: str, content_type: str = "text/plain; charset=utf-8"):
        response_bytes = text.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_GET(self):
        start_ts = time.time()
        current = state.get_state()

        # Simulate response latency
        if current["latency_ms"] > 0:
            time.sleep(current["latency_ms"] / 1000.0)

        path = self.path.split("?")[0]

        if path in ("/health", "/healthz", "/api/health"):
            # Determine if error rate triggers failure or service is unhealthy
            is_unhealthy = current["status"] == "unhealthy" or (current["error_rate"] > 0 and random.random() < current["error_rate"])
            state.record_request(is_unhealthy)

            status_code = 503 if is_unhealthy else (429 if current["status"] == "degraded" and current["error_rate"] > 0.05 else 200)
            data = {
                "service": SERVICE_NAME,
                "environment": SERVICE_ENV,
                "status": "unhealthy" if is_unhealthy else current["status"],
                "uptime_seconds": current["uptime_seconds"],
                "latency_ms": current["latency_ms"],
                "error_rate": current["error_rate"],
            }
            self._send_json(status_code, data)
            logger.info("Health probe executed", extra={"extra_fields": {"method": "GET", "path": path, "status": status_code, "service": SERVICE_NAME}})
            return

        elif path in ("/metrics", "/api/metrics"):
            # Expose standard Prometheus metrics
            is_up = 1 if current["status"] != "unhealthy" else 0
            req_200 = max(current["total_requests"] - current["total_errors"], 0)
            req_500 = current["total_errors"]

            # Histogram buckets based on latency
            p95_sec = current["latency_ms"] / 1000.0

            lines = [
                f"# HELP up Service operational status",
                f"# TYPE up gauge",
                f'up{{service="{SERVICE_NAME}",environment="{SERVICE_ENV}"}} {is_up}',
                f"# HELP http_requests_total Total HTTP requests processed",
                f"# TYPE http_requests_total counter",
                f'http_requests_total{{service="{SERVICE_NAME}",environment="{SERVICE_ENV}",status="200"}} {req_200}',
                f'http_requests_total{{service="{SERVICE_NAME}",environment="{SERVICE_ENV}",status="500"}} {req_500}',
                f"# HELP http_requests_failed_total Total HTTP requests that returned 5xx errors",
                f"# TYPE http_requests_failed_total counter",
                f'http_requests_failed_total{{service="{SERVICE_NAME}",environment="{SERVICE_ENV}"}} {req_500}',
                f"# HELP http_request_duration_seconds HTTP request duration histogram",
                f"# TYPE http_request_duration_seconds histogram",
                f'http_request_duration_seconds_bucket{{service="{SERVICE_NAME}",environment="{SERVICE_ENV}",le="0.05"}} {int(req_200 * 0.7)}',
                f'http_request_duration_seconds_bucket{{service="{SERVICE_NAME}",environment="{SERVICE_ENV}",le="0.10"}} {int(req_200 * 0.85)}',
                f'http_request_duration_seconds_bucket{{service="{SERVICE_NAME}",environment="{SERVICE_ENV}",le="0.25"}} {int(req_200 * 0.95)}',
                f'http_request_duration_seconds_bucket{{service="{SERVICE_NAME}",environment="{SERVICE_ENV}",le="0.50"}} {int(req_200 * 0.99)}',
                f'http_request_duration_seconds_bucket{{service="{SERVICE_NAME}",environment="{SERVICE_ENV}",le="1.00"}} {req_200}',
                f'http_request_duration_seconds_bucket{{service="{SERVICE_NAME}",environment="{SERVICE_ENV}",le="+Inf"}} {current["total_requests"]}',
                f'http_request_duration_seconds_sum{{service="{SERVICE_NAME}",environment="{SERVICE_ENV}"}} {round(p95_sec * current["total_requests"], 3)}',
                f'http_request_duration_seconds_count{{service="{SERVICE_NAME}",environment="{SERVICE_ENV}"}} {current["total_requests"]}',
                f"# HELP process_cpu_usage Instantaneous CPU utilization ratio",
                f"# TYPE process_cpu_usage gauge",
                f'process_cpu_usage{{service="{SERVICE_NAME}",environment="{SERVICE_ENV}"}} {current["cpu_usage"]}',
                f"# HELP process_resident_memory_bytes Resident memory size in bytes",
                f"# TYPE process_resident_memory_bytes gauge",
                f'process_resident_memory_bytes{{service="{SERVICE_NAME}",environment="{SERVICE_ENV}"}} {current["memory_bytes"]}',
            ]
            metrics_payload = "\n".join(lines) + "\n"
            self._send_text(200, metrics_payload, "text/plain; version=0.0.4; charset=utf-8")
            return

        elif path in ("/", "/status"):
            self._send_json(200, current)
            return

        else:
            self._send_json(404, {"error": "Not Found", "path": path})

    def do_POST(self):
        path = self.path.split("?")[0]
        content_length = int(self.headers.get("Content-Length", 0))
        body = {}
        if content_length > 0:
            try:
                body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            except Exception:
                pass

        if path == "/chaos/degrade":
            latency = body.get("latency_ms", 650)
            error_rate = body.get("error_rate", 0.08)
            cpu = body.get("cpu_usage", 0.92)
            mem = body.get("memory_bytes", 2147483648)
            status_val = body.get("status", "degraded")
            state.set_chaos(status=status_val, latency_ms=latency, error_rate=error_rate, cpu_usage=cpu, memory_bytes=mem)
            logger.warning("Chaos injection: DEGRADED state applied", extra={"extra_fields": {"chaos_state": state.get_state()}})
            self._send_json(200, {"message": "Service degraded", "state": state.get_state()})

        elif path == "/chaos/fail":
            state.set_chaos(status="unhealthy", latency_ms=10, error_rate=1.0, cpu_usage=0.10)
            logger.error("Chaos injection: HARD FAILURE applied", extra={"extra_fields": {"chaos_state": state.get_state()}})
            self._send_json(200, {"message": "Service forced into failed state", "state": state.get_state()})

        elif path == "/chaos/recover":
            state.reset_health()
            logger.info("Chaos injection: RECOVERED to healthy state", extra={"extra_fields": {"chaos_state": state.get_state()}})
            self._send_json(200, {"message": "Service restored to normal health", "state": state.get_state()})

        else:
            self._send_json(404, {"error": "Not Found", "path": path})


def run():
    server = http.server.ThreadingHTTPServer(("0.0.0.0", SERVICE_PORT), TestServiceRequestHandler)
    logger.info(f"Test Microservice '{SERVICE_NAME}' listening on 0.0.0.0:{SERVICE_PORT} [{SERVICE_ENV}]")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
