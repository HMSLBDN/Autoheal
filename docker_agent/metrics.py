"""
Restricted Docker Agent — Observability & Prometheus Metrics
Tracks request volumes, authorization outcomes, execution latencies, and verification statistics.
"""

from typing import Dict


class AgentMetrics:
    """
    In-memory metrics collector producing Prometheus-compatible text output.
    """

    def __init__(self):
        self.requests_received: int = 0
        self.requests_authorized: int = 0
        self.requests_rejected: int = 0
        self.execution_successes: int = 0
        self.execution_failures: int = 0
        self.verification_successes: int = 0
        self.verification_failures: int = 0
        self.duplicate_requests: int = 0
        self.expired_requests: int = 0
        self.total_duration_ms: int = 0

    def record_request_received(self):
        self.requests_received += 1

    def record_authorized(self):
        self.requests_authorized += 1

    def record_rejected(self, reason: str = ""):
        self.requests_rejected += 1
        if "replay" in reason.lower() or "already" in reason.lower():
            self.duplicate_requests += 1
        elif "drift" in reason.lower() or "expired" in reason.lower():
            self.expired_requests += 1

    def record_execution(self, success: bool, duration_ms: int):
        self.total_duration_ms += duration_ms
        if success:
            self.execution_successes += 1
        else:
            self.execution_failures += 1

    def record_verification(self, success: bool):
        if success:
            self.verification_successes += 1
        else:
            self.verification_failures += 1

    def format_prometheus_metrics(self) -> str:
        """Produces standard Prometheus exposition format."""
        lines = [
            "# HELP autoheal_docker_agent_requests_received_total Total requests received by restricted agent",
            "# TYPE autoheal_docker_agent_requests_received_total counter",
            f"autoheal_docker_agent_requests_received_total {self.requests_received}",
            "",
            "# HELP autoheal_docker_agent_requests_authorized_total Requests passing HMAC, nonce, and allowlist validation",
            "# TYPE autoheal_docker_agent_requests_authorized_total counter",
            f"autoheal_docker_agent_requests_authorized_total {self.requests_authorized}",
            "",
            "# HELP autoheal_docker_agent_requests_rejected_total Requests rejected due to security or policy checks",
            "# TYPE autoheal_docker_agent_requests_rejected_total counter",
            f"autoheal_docker_agent_requests_rejected_total {self.requests_rejected}",
            "",
            "# HELP autoheal_docker_agent_executions_total Recovery execution attempts partitioned by outcome",
            "# TYPE autoheal_docker_agent_executions_total counter",
            f'autoheal_docker_agent_executions_total{{status="success"}} {self.execution_successes}',
            f'autoheal_docker_agent_executions_total{{status="failure"}} {self.execution_failures}',
            "",
            "# HELP autoheal_docker_agent_verifications_total Post-recovery verification outcomes",
            "# TYPE autoheal_docker_agent_verifications_total counter",
            f'autoheal_docker_agent_verifications_total{{status="passed"}} {self.verification_successes}',
            f'autoheal_docker_agent_verifications_total{{status="failed"}} {self.verification_failures}',
            "",
            "# HELP autoheal_docker_agent_replays_total Rejected duplicate or replayed request attempts",
            "# TYPE autoheal_docker_agent_replays_total counter",
            f"autoheal_docker_agent_replays_total {self.duplicate_requests}",
            "",
            "# HELP autoheal_docker_agent_expired_total Rejected requests with timestamp drift exceeding threshold",
            "# TYPE autoheal_docker_agent_expired_total counter",
            f"autoheal_docker_agent_expired_total {self.expired_requests}",
            "",
            "# HELP autoheal_docker_agent_execution_duration_ms_total Cumulative execution duration in milliseconds",
            "# TYPE autoheal_docker_agent_execution_duration_ms_total counter",
            f"autoheal_docker_agent_execution_duration_ms_total {self.total_duration_ms}",
        ]
        return "\n".join(lines) + "\n"

    def reset(self):
        """Resets all metrics counters (for test isolation)."""
        self.__init__()


agent_metrics = AgentMetrics()
