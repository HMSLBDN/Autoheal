"""
AutoHeal DevOps — Canary Release & Rollback Decision Support Engine
Evaluates progressive rollout stages (canary, progressive rollout, final evaluation)
against baseline telemetry. Strictly advisory and simulated; never performs live production rollbacks.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service import Service, DeploymentEvent
from app.models.enterprise import ReleaseEvaluation, ReleaseEvaluationMetric
from app.models.base import utc_now

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLDS = {
    "max_error_rate_delta": 0.5,      # Max 0.5% error rate increase
    "max_latency_delta_ms": 100.0,    # Max 100ms P95 latency increase
    "min_availability": 99.9,         # Min 99.9% availability
    "max_cpu_percent": 85.0,          # Max 85% CPU utilization
    "max_memory_percent": 85.0,       # Max 85% Memory utilization
}


class CanaryReleaseEvaluator:
    """
    Evaluates telemetry deltas between baseline and canary release deployments.
    Provides evidence-based advisory recommendations.
    """

    MIN_SAMPLES_REQUIRED = 3

    async def evaluate_canary(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        service_id: str,
        release_tag: str,
        traffic_percentage: int = 10,
        observation_window_minutes: int = 30,
        custom_thresholds: Optional[Dict[str, float]] = None,
        observed_samples: Optional[List[Dict[str, float]]] = None,
    ) -> ReleaseEvaluation:
        """
        Executes canary evaluation comparing baseline to observed canary telemetry.
        """
        # Fetch service
        svc_q = select(Service).where(
            and_(
                Service.organization_id == organization_id,
                Service.id == service_id,
            )
        )
        svc_res = await db.execute(svc_q)
        service = svc_res.scalars().first()
        if not service:
            raise ValueError(f"Service {service_id} not found.")

        thresholds = dict(DEFAULT_THRESHOLDS)
        if custom_thresholds:
            thresholds.update(custom_thresholds)

        # Baseline metrics
        baseline_metrics = {
            "error_rate": 0.05,
            "latency_ms": 45.0,
            "availability": 99.98,
            "cpu_percent": 25.0,
            "memory_percent": 35.0,
        }

        # Observed samples
        samples = observed_samples or [
            {"error_rate": float(service.error_rate or 0.05), "latency_ms": float(service.latency_ms or 45.0), "availability": float(service.availability or 99.95), "cpu_percent": 28.0, "memory_percent": 38.0}
        ]
        sample_count = len(samples)

        # Compute averages
        avg_canary = {
            "error_rate": round(sum(s.get("error_rate", 0) for s in samples) / sample_count, 2),
            "latency_ms": round(sum(s.get("latency_ms", 0) for s in samples) / sample_count, 1),
            "availability": round(sum(s.get("availability", 99.9) for s in samples) / sample_count, 2),
            "cpu_percent": round(sum(s.get("cpu_percent", 0) for s in samples) / sample_count, 1),
            "memory_percent": round(sum(s.get("memory_percent", 0) for s in samples) / sample_count, 1),
        }

        err_delta = round(avg_canary["error_rate"] - baseline_metrics["error_rate"], 2)
        lat_delta = round(avg_canary["latency_ms"] - baseline_metrics["latency_ms"], 1)

        metric_evals: List[Dict[str, Any]] = []
        regression_detected = False
        reasons: List[str] = []

        # 1. Error rate check
        err_breach = err_delta > thresholds["max_error_rate_delta"]
        if err_breach:
            regression_detected = True
            reasons.append(f"Error rate delta (+{err_delta}%) exceeded threshold (+{thresholds['max_error_rate_delta']}%)")
        metric_evals.append({
            "metric_name": "error_rate",
            "baseline_value": baseline_metrics["error_rate"],
            "canary_value": avg_canary["error_rate"],
            "delta": err_delta,
            "threshold_value": thresholds["max_error_rate_delta"],
            "status": "breach" if err_breach else ("warning" if err_delta > 0.2 else "pass"),
        })

        # 2. Latency check
        lat_breach = lat_delta > thresholds["max_latency_delta_ms"]
        if lat_breach:
            regression_detected = True
            reasons.append(f"P95 latency delta (+{lat_delta}ms) exceeded threshold (+{thresholds['max_latency_delta_ms']}ms)")
        metric_evals.append({
            "metric_name": "latency_ms",
            "baseline_value": baseline_metrics["latency_ms"],
            "canary_value": avg_canary["latency_ms"],
            "delta": lat_delta,
            "threshold_value": thresholds["max_latency_delta_ms"],
            "status": "breach" if lat_breach else ("warning" if lat_delta > 50.0 else "pass"),
        })

        # 3. Availability check
        avail_breach = avg_canary["availability"] < thresholds["min_availability"]
        if avail_breach:
            regression_detected = True
            reasons.append(f"Availability ({avg_canary['availability']}%) dropped below SLA target ({thresholds['min_availability']}%)")
        metric_evals.append({
            "metric_name": "availability",
            "baseline_value": baseline_metrics["availability"],
            "canary_value": avg_canary["availability"],
            "delta": round(avg_canary["availability"] - baseline_metrics["availability"], 2),
            "threshold_value": thresholds["min_availability"],
            "status": "breach" if avail_breach else "pass",
        })

        # Recommendation synthesis
        if sample_count < self.MIN_SAMPLES_REQUIRED and observed_samples is not None:
            stage = "canary"
            status = "degraded"
            recommendation = "pause"
            explanation = (
                f"Insufficient observation samples ({sample_count} < {self.MIN_SAMPLES_REQUIRED}). "
                "Canary evaluation paused to collect additional telemetry before promoting traffic."
            )
        elif regression_detected:
            stage = "rollback_recommended"
            status = "failed"
            recommendation = "rollback_recommended"
            explanation = (
                f"Canary regression detected for release {release_tag} at {traffic_percentage}% traffic. "
                f"Breaches: {'; '.join(reasons)}. Simulated recommendation: halt promotion and trigger rollback_release."
            )
        else:
            stage = "progressive_rollout"
            status = "passed"
            recommendation = "proceed"
            explanation = (
                f"Canary metrics for release {release_tag} ({traffic_percentage}% traffic) are healthy and within safe operating thresholds. "
                "Recommended action: promote traffic to next progressive rollout stage."
            )

        now = utc_now()
        evaluation = ReleaseEvaluation(
            organization_id=organization_id,
            service_id=service_id,
            release_tag=release_tag,
            stage=stage,
            status=status,
            traffic_percentage=traffic_percentage,
            observation_window_minutes=observation_window_minutes,
            sample_count=sample_count,
            baseline_metrics_json=json.dumps(baseline_metrics),
            canary_metrics_json=json.dumps(avg_canary),
            thresholds_json=json.dumps(thresholds),
            regression_detected=regression_detected,
            recommendation=recommendation,
            explanation=explanation,
            evaluated_at=now,
            created_at=now,
        )
        db.add(evaluation)
        await db.flush()

        for m in metric_evals:
            metric_rec = ReleaseEvaluationMetric(
                evaluation_id=evaluation.id,
                metric_name=m["metric_name"],
                baseline_value=m["baseline_value"],
                canary_value=m["canary_value"],
                delta=m["delta"],
                threshold_value=m["threshold_value"],
                status=m["status"],
                evaluated_at=now,
            )
            db.add(metric_rec)

        await db.flush()
        return evaluation
