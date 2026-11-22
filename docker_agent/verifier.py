"""
Restricted Docker Agent — Application Health Verification Module
Independently verifies that the application running inside the container has actually restored service.
A successful container restart is NEVER treated as proof of recovery.
"""

from datetime import datetime, timezone
import json
import logging
import time
from typing import Dict, Optional, Tuple
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


class ApplicationHealthVerifier:
    """
    Probes the HTTP health endpoint of a target application to verify SLA restoration.
    """

    def __init__(self, default_timeout_seconds: float = 5.0):
        self.default_timeout = default_timeout_seconds

    async def verify_application_health(
        self,
        target_host: str = "localhost",
        port: int = 8080,
        health_path: str = "/health",
        expected_status: int = 200,
        mock_healthy: Optional[bool] = None,
    ) -> Tuple[bool, int, str, int]:
        """
        Executes an HTTP GET probe against the target service health endpoint.
        Returns: (is_healthy: bool, status_code: int, summary: str, duration_ms: int)
        """
        start_time = time.time()

        # Mock mode override (for testing environments without active network listener)
        if mock_healthy is not None:
            duration_ms = 12
            if mock_healthy:
                return (
                    True,
                    200,
                    f"HTTP 200 OK from http://{target_host}:{port}{health_path} (status: healthy)",
                    duration_ms,
                )
            else:
                return (
                    False,
                    503,
                    f"HTTP 503 Service Unavailable from http://{target_host}:{port}{health_path} (status: degraded)",
                    duration_ms,
                )

        url = f"http://{target_host}:{port}{health_path}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AutoHeal-Health-Verifier/1.0"})
            with urllib.request.urlopen(req, timeout=self.default_timeout) as resp:
                status_code = resp.getcode()
                body = resp.read().decode("utf-8", errors="replace")
                duration_ms = int((time.time() - start_time) * 1000)

                # Check status code
                if status_code != expected_status:
                    return (
                        False,
                        status_code,
                        f"Health check failed: expected HTTP {expected_status}, received {status_code}",
                        duration_ms,
                    )

                # Try parsing JSON to verify payload
                try:
                    payload = json.loads(body)
                    app_status = payload.get("status", "").lower()
                    if app_status in ("healthy", "ok", "ready", "running"):
                        return (
                            True,
                            status_code,
                            f"Health verified: {url} returned HTTP {status_code} ({app_status})",
                            duration_ms,
                        )
                    elif app_status in ("degraded", "unhealthy", "failing"):
                        return (
                            False,
                            status_code,
                            f"Health probe rejected: application reports internal status '{app_status}'",
                            duration_ms,
                        )
                except Exception:
                    pass  # Non-JSON 200 response

                return (
                    True,
                    status_code,
                    f"Health check passed: {url} responded HTTP {status_code}",
                    duration_ms,
                )

        except urllib.error.HTTPError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return (
                False,
                e.code,
                f"Health check HTTP error {e.code}: {e.reason}",
                duration_ms,
            )
        except urllib.error.URLError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return (
                False,
                0,
                f"Health check connection failed: {e.reason}",
                duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return (
                False,
                0,
                f"Health check exception: {str(e)}",
                duration_ms,
            )
