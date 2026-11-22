"""
Restricted Docker Agent — Docker Engine API Client
Communicates with the host Docker daemon exclusively through the hardened L7 NGINX micro-proxy
over Mutual TLS (mTLS), or directly via Unix domain socket when configured for local development.
Includes strict simulation mode enforcement and verified mock fallback.
"""

from datetime import datetime, timezone
import http.client
import json
import logging
import os
import socket
import ssl
from typing import Any, Dict, Optional, Tuple
import urllib.parse

from docker_agent.config import settings
from docker_agent.models import ContainerStatus

logger = logging.getLogger(__name__)


class DockerEngineClient:
    """
    Communicates with Docker Engine API via mTLS L7 Proxy or Unix Domain Socket.
    Only exposes narrow, allowlisted container inspect and restart methods.
    """

    def __init__(
        self,
        socket_path: Optional[str] = None,
        host_url: Optional[str] = None,
        mock_mode: Optional[bool] = None,
    ):
        self.socket_path = socket_path or settings.DOCKER_SOCKET_PATH
        self.host_url = host_url or settings.DOCKER_HOST_URL
        self.ca_cert_path = settings.PROXY_CA_CERT_PATH
        self.client_cert_path = settings.AGENT_CLIENT_CERT_PATH
        self.client_key_path = settings.AGENT_CLIENT_KEY_PATH

        # Determine if mTLS proxy is configured
        self.is_proxy_configured = (
            bool(self.host_url)
            and self.host_url.startswith("https://")
            and os.path.exists(self.ca_cert_path)
            and os.path.exists(self.client_cert_path)
            and os.path.exists(self.client_key_path)
        )

        has_socket = bool(self.socket_path) and os.path.exists(self.socket_path)

        if mock_mode is not None:
            self.mock_mode = mock_mode
        else:
            self.mock_mode = not (self.is_proxy_configured or has_socket) and settings.ENABLE_MOCK_FALLBACK

        # In-memory mock container state for isolated test execution
        self._mock_containers: Dict[str, Dict[str, Any]] = {
            "autoheal_test_service": {
                "status": "running",
                "state": "running",
                "health": "healthy",
                "restart_count": 0,
                "uptime_seconds": 3600,
                "image": "autoheal_test_service:latest",
            },
            "test-service": {
                "status": "running",
                "state": "running",
                "health": "healthy",
                "restart_count": 0,
                "uptime_seconds": 1800,
                "image": "test-service:latest",
            },
        }

    def _call_mtls_proxy(
        self, method: str, path: str, body: Optional[Dict[str, Any]] = None, timeout: int = 15
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Issues an HTTPS request with Mutual TLS to the hardened NGINX micro-proxy.
        Enforces strict CA trust and SAN hostname verification.
        """
        parsed = urllib.parse.urlparse(self.host_url)
        host = parsed.hostname or "autoheal_socket_proxy"
        port = parsed.port or 8443

        ssl_ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH, cafile=self.ca_cert_path)
        ssl_ctx.load_cert_chain(certfile=self.client_cert_path, keyfile=self.client_key_path)
        # Hostname verification & cert validation are enabled by default

        conn = http.client.HTTPSConnection(host, port, context=ssl_ctx, timeout=timeout)
        headers = {
            "User-Agent": "AutoHeal-Docker-Agent/1.0",
            "Accept": "application/json",
        }
        req_body = ""
        if body:
            req_body = json.dumps(body)
            headers["Content-Type"] = "application/json"

        try:
            conn.request(method, path, body=req_body if req_body else None, headers=headers)
            response = conn.getresponse()
            status_code = response.status
            resp_bytes = response.read()
            resp_json = {}
            if resp_bytes:
                try:
                    resp_json = json.loads(resp_bytes.decode("utf-8", errors="replace"))
                except Exception:
                    resp_json = {"raw": resp_bytes.decode("utf-8", errors="replace")}
            return status_code, resp_json
        finally:
            conn.close()

    def _call_docker_socket(
        self, method: str, path: str, body: Optional[Dict[str, Any]] = None, timeout: int = 15
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Issues an HTTP request directly to Docker Engine via Unix domain socket.
        """
        if not os.path.exists(self.socket_path):
            raise ConnectionError(f"Docker socket not found at '{self.socket_path}'.")

        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect(self.socket_path)
            req_lines = [
                f"{method} {path} HTTP/1.1",
                "Host: localhost",
                "User-Agent: AutoHeal-Docker-Agent/1.0",
                "Connection: close",
            ]
            req_body = ""
            if body:
                req_body = json.dumps(body)
                req_lines.append("Content-Type: application/json")
                req_lines.append(f"Content-Length: {len(req_body)}")
            req_lines.append("\r\n")

            full_request = "\r\n".join(req_lines) + req_body
            s.sendall(full_request.encode("utf-8"))

            response_bytes = bytearray()
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                response_bytes.extend(chunk)

            raw_response = response_bytes.decode("utf-8", errors="replace")
            header_end = raw_response.find("\r\n\r\n")
            if header_end == -1:
                return 500, {"error": "Invalid HTTP response from Docker socket"}

            header_text = raw_response[:header_end]
            body_text = raw_response[header_end + 4 :]

            status_line = header_text.splitlines()[0]
            status_code = int(status_line.split()[1])

            resp_json = {}
            if body_text.strip():
                try:
                    resp_json = json.loads(body_text)
                except Exception:
                    resp_json = {"raw": body_text}

            return status_code, resp_json

        finally:
            s.close()

    def _call_docker(
        self, method: str, path: str, body: Optional[Dict[str, Any]] = None, timeout: int = 15
    ) -> Tuple[int, Dict[str, Any]]:
        """Routes Docker API call through mTLS proxy or direct socket."""
        if self.is_proxy_configured:
            return self._call_mtls_proxy(method, path, body, timeout)
        return self._call_docker_socket(method, path, body, timeout)

    def ping(self) -> bool:
        """Checks if Docker daemon or proxy is responsive."""
        if self.mock_mode:
            return True
        try:
            status, _ = self._call_docker("GET", "/containers/autoheal_test_service/json", timeout=5)
            return status in (200, 404)
        except Exception as e:
            logger.debug("Docker ping failed: %s", e)
            return False

    def inspect_container(self, container_name: str) -> ContainerStatus:
        """
        Inspects container lifecycle and health status.
        """
        now = datetime.now(timezone.utc)

        if self.mock_mode or settings.SIMULATION_MODE:
            c = self._mock_containers.get(
                container_name,
                {
                    "status": "running",
                    "state": "running",
                    "health": "healthy",
                    "restart_count": 0,
                    "uptime_seconds": 3600,
                    "image": f"{container_name}:latest",
                },
            )
            return ContainerStatus(
                container_name=container_name,
                status=c["status"],
                state=c["state"],
                health=c["health"],
                restart_count=c["restart_count"],
                uptime_seconds=c["uptime_seconds"],
                image=c["image"],
                checked_at=now,
                is_mocked=True,
            )

        # Real inspect call: GET /containers/{name}/json
        status_code, data = self._call_docker("GET", f"/containers/{container_name}/json")
        if status_code == 404:
            raise FileNotFoundError(f"Container '{container_name}' not found on Docker host.")
        if status_code != 200:
            raise RuntimeError(f"Docker API error inspecting '{container_name}': HTTP {status_code}")

        state_data = data.get("State", {})
        health_data = state_data.get("Health", {})

        return ContainerStatus(
            container_name=container_name,
            status=state_data.get("Status", "unknown"),
            state=state_data.get("Status", "unknown"),
            health=health_data.get("Status", "none"),
            restart_count=data.get("RestartCount", 0),
            uptime_seconds=120,
            image=data.get("Config", {}).get("Image", ""),
            checked_at=now,
            is_mocked=False,
        )

    def restart_container(self, container_name: str, timeout_seconds: int = 15) -> Dict[str, Any]:
        """
        Restarts the target container gracefully.
        In simulation mode, real restart is completely blocked and returns mock receipt.
        """
        start_time = datetime.now(timezone.utc)

        if self.mock_mode or settings.SIMULATION_MODE:
            c = self._mock_containers.setdefault(
                container_name,
                {
                    "status": "running",
                    "state": "running",
                    "health": "healthy",
                    "restart_count": 0,
                    "uptime_seconds": 3600,
                    "image": f"{container_name}:latest",
                },
            )
            c["restart_count"] += 1
            c["uptime_seconds"] = 1
            c["status"] = "running"
            c["state"] = "running"
            c["health"] = "healthy"
            duration_ms = 85

            return {
                "container_name": container_name,
                "status": "success",
                "exit_code": 0,
                "duration_ms": duration_ms,
                "restart_count": c["restart_count"],
                "is_mocked": True,
                "stdout": f"[SIMULATION_MODE] Container '{container_name}' simulated restart cleanly in {duration_ms}ms.",
                "stderr": "",
                "started_at": start_time.isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

        # Real Docker API call: POST /containers/{name}/restart?t={timeout}
        path = f"/containers/{container_name}/restart?t={timeout_seconds}"
        status_code, data = self._call_docker("POST", path, timeout=timeout_seconds + 5)

        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        if status_code in (200, 204):
            return {
                "container_name": container_name,
                "status": "success",
                "exit_code": 0,
                "duration_ms": duration_ms,
                "is_mocked": False,
                "stdout": f"[DOCKER_ENGINE] Container '{container_name}' restarted cleanly (HTTP {status_code}).",
                "stderr": "",
                "started_at": start_time.isoformat(),
                "completed_at": end_time.isoformat(),
            }
        elif status_code == 404:
            raise FileNotFoundError(f"Container '{container_name}' not found on Docker host.")
        else:
            return {
                "container_name": container_name,
                "status": "failed",
                "exit_code": 1,
                "duration_ms": duration_ms,
                "is_mocked": False,
                "stdout": "",
                "stderr": f"Docker restart failed with HTTP {status_code}: {data.get('message', '')}",
                "started_at": start_time.isoformat(),
                "completed_at": end_time.isoformat(),
            }
