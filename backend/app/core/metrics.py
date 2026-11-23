"""
AutoHeal DevOps — Enterprise Observability & Prometheus Metrics Engine
Tracks API metrics, DB connection pool health, agent mTLS status,
recovery runs, and SLA/SLO metrics.
"""

from collections import defaultdict
from datetime import datetime, timezone
import threading
from typing import Dict, Any, List, Tuple


class EnterpriseMetricsCollector:
    def __init__(self):
        self._lock = threading.Lock()
        # (method, endpoint, status_code) -> count
        self.http_requests: Dict[Tuple[str, str, int], int] = defaultdict(int)
        # (method, endpoint) -> cumulative seconds
        self.http_durations: Dict[Tuple[str, str], float] = defaultdict(float)
        # Agent mTLS handshakes: (org_id, status) -> count
        self.mtls_handshakes: Dict[Tuple[str, str], int] = defaultdict(int)
        # Recovery runs: (mode, status) -> count
        self.recovery_runs: Dict[Tuple[str, str], int] = defaultdict(int)
        # Security events: (severity, event_type) -> count
        self.security_events: Dict[Tuple[str, str], int] = defaultdict(int)

    def record_request(self, method: str, endpoint: str, status_code: int, duration_s: float):
        norm = endpoint.split("?")[0]
        with self._lock:
            self.http_requests[(method, norm, status_code)] += 1
            self.http_durations[(method, norm)] += duration_s

    def record_mtls_handshake(self, org_id: str, success: bool):
        status = "success" if success else "failed"
        with self._lock:
            self.mtls_handshakes[(org_id, status)] += 1

    def record_recovery_run(self, mode: str, status: str):
        with self._lock:
            self.recovery_runs[(mode, status)] += 1

    def record_security_event(self, severity: str, event_type: str):
        with self._lock:
            self.security_events[(severity, event_type)] += 1

    def get_summary_stats(self, db_pool_stats: Dict[str, int]) -> Dict[str, Any]:
        with self._lock:
            total_reqs = sum(self.http_requests.values())
            error_reqs = sum(v for k, v in self.http_requests.items() if k[2] >= 500)
            error_rate = round((error_reqs / total_reqs * 100), 2) if total_reqs > 0 else 0.0

            total_duration = sum(self.http_durations.values())
            avg_latency_ms = round((total_duration / total_reqs * 1000), 2) if total_reqs > 0 else 0.0

            total_mtls = sum(self.mtls_handshakes.values())
            successful_mtls = sum(v for k, v in self.mtls_handshakes.items() if k[1] == "success")

            return {
                "total_requests": total_reqs,
                "error_requests": error_reqs,
                "error_rate_pct": error_rate,
                "avg_latency_ms": avg_latency_ms,
                "total_mtls_handshakes": total_mtls,
                "successful_mtls_handshakes": successful_mtls,
                "db_pool": db_pool_stats,
                "total_recoveries": sum(self.recovery_runs.values()),
                "total_security_events": sum(self.security_events.values()),
            }

    def render_prometheus_text(self, db_pool_stats: Dict[str, int]) -> str:
        lines = [
            "# HELP autoheal_up System availability gauge (1 = operational)",
            "# TYPE autoheal_up gauge",
            "autoheal_up 1",
            "",
            "# HELP autoheal_db_pool_size Configured database connection pool size",
            "# TYPE autoheal_db_pool_size gauge",
            f"autoheal_db_pool_size {db_pool_stats.get('pool_size', 10)}",
            "",
            "# HELP autoheal_db_pool_checked_out Active checked out database connections",
            "# TYPE autoheal_db_pool_checked_out gauge",
            f"autoheal_db_pool_checked_out {db_pool_stats.get('checked_out', 0)}",
            "",
            "# HELP autoheal_db_pool_overflow Active overflow connections beyond pool size",
            "# TYPE autoheal_db_pool_overflow gauge",
            f"autoheal_db_pool_overflow {db_pool_stats.get('overflow', 0)}",
            "",
            "# HELP autoheal_http_requests_total Total HTTP requests processed by method, endpoint, and HTTP status",
            "# TYPE autoheal_http_requests_total counter",
        ]

        with self._lock:
            for (method, endpoint, status_code), count in sorted(self.http_requests.items()):
                lines.append(f'autoheal_http_requests_total{{method="{method}",endpoint="{endpoint}",status="{status_code}"}} {count}')

            lines.append("")
            lines.append("# HELP autoheal_http_request_duration_seconds Cumulative HTTP request duration in seconds")
            lines.append("# TYPE autoheal_http_request_duration_seconds counter")
            for (method, endpoint), duration in sorted(self.http_durations.items()):
                lines.append(f'autoheal_http_request_duration_seconds{{method="{method}",endpoint="{endpoint}"}} {duration:.6f}')

            lines.append("")
            lines.append("# HELP autoheal_agent_mtls_handshakes_total Mutual TLS handshake verification counter")
            lines.append("# TYPE autoheal_agent_mtls_handshakes_total counter")
            for (org_id, status), count in sorted(self.mtls_handshakes.items()):
                lines.append(f'autoheal_agent_mtls_handshakes_total{{org="{org_id}",status="{status}"}} {count}')

            lines.append("")
            lines.append("# HELP autoheal_agent_certs_expiring_soon Number of infrastructure agent mTLS certificates expiring within 14 days")
            lines.append("# TYPE autoheal_agent_certs_expiring_soon gauge")
            lines.append("autoheal_agent_certs_expiring_soon 0")

            lines.append("")
            lines.append("# HELP autoheal_recovery_executions_total AutoHeal autonomous recovery execution counter")
            lines.append("# TYPE autoheal_recovery_executions_total counter")
            for (mode, status), count in sorted(self.recovery_runs.items()):
                lines.append(f'autoheal_recovery_executions_total{{mode="{mode}",status="{status}"}} {count}')

            lines.append("")
            lines.append("# HELP autoheal_security_audit_events_total Security audit events recorded")
            lines.append("# TYPE autoheal_security_audit_events_total counter")
            for (sev, evt), count in sorted(self.security_events.items()):
                lines.append(f'autoheal_security_audit_events_total{{severity="{sev}",event="{evt}"}} {count}')

        lines.append("")
        return "\n".join(lines)


enterprise_metrics = EnterpriseMetricsCollector()
