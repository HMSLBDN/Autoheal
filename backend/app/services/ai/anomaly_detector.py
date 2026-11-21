"""
AutoHeal DevOps — Anomaly Detection & Predictive Monitoring Engine
Statistical algorithms: Rolling Z-Score, EWMA, Trend Slope.
Detects CPU spikes, memory leaks, latency degradation, error bursts, and capacity exhaustion.
Includes noise filtering, minimum sample validation, deduplication, and multi-horizon forecasting.
"""

from datetime import datetime, timedelta, timezone
import math
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence import AnomalyEvent, PredictiveInsight
from app.models.service import Service
from app.models.base import utc_now


class AnomalyDetectionEngine:
    """
    Mathematical and statistical anomaly detection and metric forecasting engine.
    Safe, deterministic, tenant-isolated, and explainable.
    """

    MIN_SAMPLES_REQUIRED = 3
    DEFAULT_DEDUP_WINDOW_MINUTES = 15

    # Standard default thresholds for DevOps metrics
    THRESHOLDS = {
        "cpu_percent": {"warning": 75.0, "critical": 90.0, "z_thresh": 2.5},
        "memory_percent": {"warning": 75.0, "critical": 85.0, "z_thresh": 2.5},
        "latency_ms": {"warning": 300.0, "critical": 500.0, "z_thresh": 2.5},
        "error_rate": {"warning": 1.0, "critical": 5.0, "z_thresh": 2.5},
        "disk_percent": {"warning": 80.0, "critical": 90.0, "z_thresh": 2.5},
    }

    @staticmethod
    def calculate_mean_and_std(values: List[float]) -> Tuple[float, float]:
        """Calculates arithmetic mean and standard deviation."""
        n = len(values)
        if n == 0:
            return 0.0, 0.0
        mean = sum(values) / n
        if n < 2:
            return mean, 0.0
        variance = sum((x - mean) ** 2 for x in values) / (n - 1)
        return mean, math.sqrt(variance)

    @staticmethod
    def calculate_z_score(current: float, mean: float, std: float) -> float:
        """Calculates Z-score: z = (x - mean) / std."""
        if std <= 1e-6:
            return 0.0
        return (current - mean) / std

    @staticmethod
    def calculate_linear_slope(values: List[float]) -> Tuple[float, float]:
        """
        Calculates simple linear regression slope (rate of change per sample unit)
        and coefficient of determination (R^2).
        """
        n = len(values)
        if n < 2:
            return 0.0, 0.0
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(values) / n

        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator <= 1e-9:
            return 0.0, 0.0

        slope = numerator / denominator

        # R^2 calculation for monotonicity / consistency
        ss_tot = sum((y - y_mean) ** 2 for y in values)
        if ss_tot <= 1e-9:
            r2 = 1.0 if slope == 0.0 else 0.0
        else:
            y_pred = [y_mean + slope * (xi - x_mean) for xi in x]
            ss_res = sum((values[i] - y_pred[i]) ** 2 for i in range(n))
            r2 = max(0.0, 1.0 - (ss_res / ss_tot))

        return slope, r2

    @staticmethod
    def calculate_ewma(values: List[float], alpha: float = 0.3) -> float:
        """Calculates Exponentially Weighted Moving Average (EWMA)."""
        if not values:
            return 0.0
        ewma = values[0]
        for val in values[1:]:
            ewma = alpha * val + (1.0 - alpha) * ewma
        return ewma

    def detect_metric_anomaly(
        self,
        metric_name: str,
        current_value: float,
        history: List[float],
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates whether a metric reading represents an anomaly.
        Requires at least MIN_SAMPLES_REQUIRED history points.
        Returns anomaly dictionary if detected, None otherwise.
        """
        all_values = list(history) + [current_value]
        if len(all_values) < self.MIN_SAMPLES_REQUIRED:
            return None

        threshold_cfg = self.THRESHOLDS.get(
            metric_name,
            {"warning": 75.0, "critical": 90.0, "z_thresh": 2.5},
        )
        mean, std = self.calculate_mean_and_std(history)
        z_score = self.calculate_z_score(current_value, mean, std)
        slope, r2 = self.calculate_linear_slope(all_values)

        is_anomaly = False
        severity = "informational"
        reasons: List[str] = []
        anomaly_score = 0.0

        # 1. Z-Score anomaly
        if abs(z_score) >= threshold_cfg["z_thresh"]:
            is_anomaly = True
            reasons.append(
                f"Statistically significant deviation (Z-score: {z_score:.2f}, baseline mean: {mean:.2f}, std: {std:.2f})"
            )
            anomaly_score = min(1.0, abs(z_score) / 5.0)

        # 2. Hard threshold breach
        if current_value >= threshold_cfg["critical"]:
            is_anomaly = True
            severity = "critical"
            reasons.append(f"Exceeded critical threshold ({current_value:.2f} >= {threshold_cfg['critical']})")
            anomaly_score = max(anomaly_score, 0.9)
        elif current_value >= threshold_cfg["warning"]:
            is_anomaly = True
            if severity != "critical":
                severity = "high"
            reasons.append(f"Exceeded warning threshold ({current_value:.2f} >= {threshold_cfg['warning']})")
            anomaly_score = max(anomaly_score, 0.7)

        # 3. Memory leak pattern: monotonic positive growth with consistent slope
        if metric_name == "memory_percent" and slope > 0.5 and r2 > 0.7 and current_value > 50.0:
            is_anomaly = True
            severity = "high" if current_value < threshold_cfg["critical"] else "critical"
            reasons.append(
                f"Monotonic memory growth pattern detected (slope: +{slope:.2f}%/step, R^2 consistency: {r2:.2f})"
            )
            anomaly_score = max(anomaly_score, 0.85)

        # 4. Latency degradation check
        if metric_name == "latency_ms" and current_value >= 500.0:
            is_anomaly = True
            severity = "critical" if current_value >= 1000.0 else "high"
            reasons.append(f"High P95 response latency ({current_value:.1f}ms)")
            anomaly_score = max(anomaly_score, 0.8)

        # 5. Error rate breach
        if metric_name == "error_rate" and current_value >= 1.0:
            is_anomaly = True
            severity = "critical" if current_value >= 5.0 else "high"
            reasons.append(f"Elevated HTTP error rate ({current_value:.2f}%)")
            anomaly_score = max(anomaly_score, 0.85)

        if not is_anomaly:
            return None

        if severity == "informational":
            if anomaly_score >= 0.8:
                severity = "critical"
            elif anomaly_score >= 0.6:
                severity = "high"
            else:
                severity = "medium"

        return {
            "metric_name": metric_name,
            "current_value": round(float(current_value), 2),
            "baseline_value": round(float(mean), 2),
            "z_score": round(float(z_score), 2),
            "anomaly_score": round(float(anomaly_score), 2),
            "severity": severity,
            "details": "; ".join(reasons),
            "slope": round(float(slope), 4),
            "r2": round(float(r2), 4),
        }

    def forecast_breach(
        self,
        metric_name: str,
        current_value: float,
        history: List[float],
        sample_interval_minutes: float = 1.0,
        horizons_minutes: List[int] = [15, 30, 60],
    ) -> List[Dict[str, Any]]:
        """
        Forecasts future metric values across specified horizons using linear trend extrapolation
        and EWMA weighting.
        """
        all_values = list(history) + [current_value]
        if len(all_values) < self.MIN_SAMPLES_REQUIRED:
            return []

        threshold_cfg = self.THRESHOLDS.get(
            metric_name,
            {"warning": 75.0, "critical": 90.0},
        )
        critical_thresh = threshold_cfg["critical"]

        slope_per_sample, r2 = self.calculate_linear_slope(all_values)
        slope_per_minute = slope_per_sample / max(0.1, sample_interval_minutes)
        ewma_val = self.calculate_ewma(all_values)

        forecasts: List[Dict[str, Any]] = []
        now = utc_now()

        for horizon in horizons_minutes:
            projected_value = current_value + (slope_per_minute * horizon)
            # Bound projection realistically between 0 and 100 for percentages
            if "percent" in metric_name or "rate" in metric_name:
                projected_value = max(0.0, min(100.0, projected_value))
            else:
                projected_value = max(0.0, projected_value)

            # Anomaly probability calculation based on proximity to threshold and trend confidence
            if projected_value >= critical_thresh:
                anomaly_prob = min(0.99, 0.70 + (r2 * 0.25))
                risk_level = "critical"
            elif projected_value >= threshold_cfg["warning"]:
                anomaly_prob = min(0.85, 0.50 + (r2 * 0.25))
                risk_level = "high"
            else:
                anomaly_prob = max(0.05, 0.20 * (projected_value / max(1.0, critical_thresh)))
                risk_level = "low" if anomaly_prob < 0.3 else "medium"

            target_time = now + timedelta(minutes=horizon)
            evidence = [
                f"Current {metric_name} is {current_value:.2f}",
                f"Projected trend rate: {slope_per_minute:+.2f}/min (R^2: {r2:.2f})",
                f"EWMA baseline: {ewma_val:.2f}",
            ]

            rec_action = ""
            if risk_level in ["high", "critical"]:
                if metric_name == "memory_percent":
                    rec_action = "Investigate memory consumption and prepare service restart or container memory limit increase before breach."
                elif metric_name == "cpu_percent":
                    rec_action = "Pre-scale replica count or adjust CPU quota before anticipated load saturation."
                elif metric_name == "disk_percent":
                    rec_action = "Purge ephemeral logs and expand persistent volume capacity before disk exhaustion."
                elif metric_name == "error_rate":
                    rec_action = "Review upstream dependency health and prepare circuit breaker or traffic shedding."
                else:
                    rec_action = f"Monitor {metric_name} closely; evaluate scale_service or restart_service."

            forecasts.append({
                "metric_name": metric_name,
                "current_value": round(float(current_value), 2),
                "predicted_value": round(float(projected_value), 2),
                "threshold_value": round(float(critical_thresh), 2),
                "prediction_horizon_minutes": horizon,
                "risk_level": risk_level,
                "anomaly_probability": round(float(anomaly_prob), 2),
                "algorithm": "ewma_linear_projection",
                "supporting_evidence": evidence,
                "recommended_preventive_action": rec_action,
                "predicted_at": now.isoformat(),
                "target_time": target_time.isoformat(),
            })

        return forecasts

    async def record_anomaly_event_if_new(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        service_id: str,
        service_name: str,
        anomaly_data: Dict[str, Any],
        dedup_window_minutes: int = DEFAULT_DEDUP_WINDOW_MINUTES,
    ) -> Optional[AnomalyEvent]:
        """
        Suppresses duplicate anomaly events within dedup_window_minutes for the same org, service, and metric.
        If unique, persists a new AnomalyEvent record.
        """
        metric_name = anomaly_data["metric_name"]
        cutoff = utc_now() - timedelta(minutes=dedup_window_minutes)

        # Check for recent active anomaly
        query = select(AnomalyEvent).where(
            and_(
                AnomalyEvent.organization_id == organization_id,
                AnomalyEvent.service_id == service_id,
                AnomalyEvent.metric_name == metric_name,
                AnomalyEvent.detected_at >= cutoff,
            )
        ).order_by(desc(AnomalyEvent.detected_at))

        result = await db.execute(query)
        existing = result.scalars().first()
        if existing:
            # Duplicate suppressed
            return None

        event = AnomalyEvent(
            organization_id=organization_id,
            service_id=service_id,
            service_name=service_name,
            metric_name=metric_name,
            current_value=anomaly_data["current_value"],
            baseline_value=anomaly_data["baseline_value"],
            z_score=anomaly_data["z_score"],
            anomaly_score=anomaly_data["anomaly_score"],
            severity=anomaly_data["severity"],
            status="detected",
            details=anomaly_data["details"],
            detected_at=utc_now(),
        )
        db.add(event)
        await db.flush()
        return event

    async def record_prediction_insight(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        service_id: str,
        service_name: str,
        forecast: Dict[str, Any],
    ) -> PredictiveInsight:
        """Persists a generated predictive insight record."""
        import json
        insight = PredictiveInsight(
            organization_id=organization_id,
            service_id=service_id,
            service_name=service_name,
            metric_name=forecast["metric_name"],
            current_value=forecast["current_value"],
            predicted_value=forecast["predicted_value"],
            threshold_value=forecast["threshold_value"],
            prediction_horizon_minutes=forecast["prediction_horizon_minutes"],
            risk_level=forecast["risk_level"],
            anomaly_probability=forecast["anomaly_probability"],
            algorithm=forecast["algorithm"],
            supporting_evidence_json=json.dumps(forecast.get("supporting_evidence", [])),
            recommended_preventive_action=forecast.get("recommended_preventive_action", ""),
            predicted_at=datetime.fromisoformat(forecast["predicted_at"]),
            target_time=datetime.fromisoformat(forecast["target_time"]),
        )
        db.add(insight)
        await db.flush()
        return insight
