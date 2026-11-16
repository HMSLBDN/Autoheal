"""
AutoHeal DevOps — Deterministic Rule-Based Diagnosis Engine
Fallback provider that produces deterministic root cause analyses
and recovery recommendations when external AI services are offline or unconfigured.
"""

from typing import Any, Dict, List
from app.services.ai.base import (
    APPROVED_RECOVERY_ACTIONS,
    AIDiagnosisResult,
    AIProvider,
)


class HeuristicDiagnosisProvider(AIProvider):
    """
    Deterministic rule-based expert system mapping metric breaches,
    alert labels, and deployment telemetry to safe, verified recovery recommendations.
    """

    @property
    def name(self) -> str:
        return "heuristic-fallback"

    async def diagnose(self, incident_context: Dict[str, Any]) -> AIDiagnosisResult:
        service_name = str(incident_context.get("service_name", "unknown-service"))
        alert_name = str(incident_context.get("alert_name", "")).lower()
        error_rate = float(incident_context.get("error_rate", 0.0))
        latency_ms = int(incident_context.get("latency_ms", 0))
        recent_deployment = bool(incident_context.get("has_recent_deployment", False))
        cpu_percent = float(incident_context.get("cpu_percent", 0.0))
        memory_percent = float(incident_context.get("memory_percent", 0.0))

        evidence: List[str] = []
        if error_rate > 0:
            evidence.append(f"Error rate elevated at {error_rate:.2f}%")
        if latency_ms > 0:
            evidence.append(f"P95 latency observed at {latency_ms}ms")
        if recent_deployment:
            evidence.append("Release deployment detected within preceding 60 minutes")
        if cpu_percent > 70.0:
            evidence.append(f"Host CPU utilization sustained at {cpu_percent:.1f}%")
        if memory_percent > 70.0:
            evidence.append(f"Host memory utilization sustained at {memory_percent:.1f}%")

        # 1. Recent release deployment causing high error rate
        if recent_deployment and (error_rate > 1.0 or "error" in alert_name):
            return AIDiagnosisResult(
                summary=f"Elevated error rate on {service_name} following recent deployment",
                probable_root_cause="Faulty commit or backward-incompatible migration introduced in latest release",
                severity="high",
                supporting_evidence=evidence or ["Recent deployment correlated with sudden 5xx spike"],
                recommended_action="rollback_release",
                risk_level="medium",
                confidence_score=0.92,
                expected_outcome="Reverting to previous stable image will eliminate 5xx regressions and normalize latency.",
            )

        # 2. Complete service outage / container crash
        if "down" in alert_name or error_rate > 50.0:
            return AIDiagnosisResult(
                summary=f"Critical outage: {service_name} instance is non-responsive",
                probable_root_cause="Process crash or deadlocked worker threads preventing TCP connections",
                severity="critical",
                supporting_evidence=evidence or ["TCP health check failure", "Zero healthy upstream replicas"],
                recommended_action="restart_service",
                risk_level="low",
                confidence_score=0.95,
                expected_outcome="Restarting the service pod will clear deadlocked processes and re-bind listeners.",
            )

        # 3. CPU / Request rate saturation
        if cpu_percent > 85.0 or "cpu" in alert_name:
            return AIDiagnosisResult(
                summary=f"CPU saturation and throughput throttling on {service_name}",
                probable_root_cause="High request volume exceeding provisioned single-pod compute capacity",
                severity="high",
                supporting_evidence=evidence or [f"Sustained CPU > 85%"],
                recommended_action="scale_service",
                risk_level="low",
                confidence_score=0.88,
                expected_outcome="Horizontal scale-up will distribute incoming request load and lower CPU per pod.",
            )

        # 4. Latency / Cache / Connection pool saturation
        if latency_ms > 400 or memory_percent > 80.0 or "latency" in alert_name:
            return AIDiagnosisResult(
                summary=f"P95 latency degradation on {service_name}",
                probable_root_cause="In-memory cache saturation or stale database connection pool bottlenecks",
                severity="medium",
                supporting_evidence=evidence or [f"Latency at {latency_ms}ms exceeding 300ms SLA"],
                recommended_action="clear_cache",
                risk_level="low",
                confidence_score=0.85,
                expected_outcome="Evicting stale cache partitions and resetting connection pools will restore response times.",
            )

        # 5. Default safe remediation
        return AIDiagnosisResult(
            summary=f"Service performance degradation detected on {service_name}",
            probable_root_cause="Transient container resource exhaustion or unhandled upstream timeout",
            severity="medium",
            supporting_evidence=evidence or ["Telemetry variance detected by monitoring threshold"],
            recommended_action="restart_service",
            risk_level="low",
            confidence_score=0.75,
            expected_outcome="Graceful restart will cycle runtime memory and recover SLA parameters.",
        )
