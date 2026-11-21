"""
AutoHeal DevOps — Preventive Recommendation Engine
Synthesizes telemetry anomalies, forecast insights, and risk scores into actionable,
non-executable advisory recommendations to prevent production outages.
"""

from datetime import datetime
import json
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence import PreventiveRecommendation, AnomalyEvent, PredictiveInsight, ServiceRiskScore
from app.models.service import Service
from app.models.base import utc_now


class PreventiveRecommendationEngine:
    """
    Proactively generates advisory operational recommendations.
    Advisory only: does NOT directly trigger infrastructure changes.
    """

    async def generate_recommendations_for_service(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        service_id: str,
        service_name: str,
    ) -> List[PreventiveRecommendation]:
        """
        Evaluates active anomalies, forecasts, and risk scores for a service
        and produces relevant preventive recommendations.
        """
        # 1. Fetch recent anomalies for this service
        anom_q = select(AnomalyEvent).where(
            and_(
                AnomalyEvent.organization_id == organization_id,
                AnomalyEvent.service_id == service_id,
                AnomalyEvent.status == "detected",
            )
        ).order_by(desc(AnomalyEvent.detected_at)).limit(10)
        anom_res = await db.execute(anom_q)
        anomalies = anom_res.scalars().all()

        # 2. Fetch recent predictive insights
        pred_q = select(PredictiveInsight).where(
            and_(
                PredictiveInsight.organization_id == organization_id,
                PredictiveInsight.service_id == service_id,
            )
        ).order_by(desc(PredictiveInsight.predicted_at)).limit(5)
        pred_res = await db.execute(pred_q)
        predictions = pred_res.scalars().all()

        # 3. Fetch latest risk score
        risk_q = select(ServiceRiskScore).where(
            and_(
                ServiceRiskScore.organization_id == organization_id,
                ServiceRiskScore.service_id == service_id,
            )
        ).order_by(desc(ServiceRiskScore.calculated_at))
        risk_res = await db.execute(risk_q)
        latest_risk = risk_res.scalars().first()

        recommendations_to_create: List[Dict[str, Any]] = []

        # Check for memory leak pattern
        mem_anom = next((a for a in anomalies if a.metric_name == "memory_percent" and "leak" in a.details.lower()), None)
        mem_pred = next((p for p in predictions if p.metric_name == "memory_percent" and p.risk_level in ["high", "critical"]), None)

        if mem_anom or mem_pred or (latest_risk and latest_risk.memory_trend == "leaking"):
            recommendations_to_create.append({
                "title": f"Investigate Persistent Memory Growth on {service_name}",
                "description": (
                    f"Predictive monitoring detected a monotonic memory increase on {service_name}. "
                    "Unchecked heap allocation could lead to container OOMKilled termination within the next 30-60 minutes."
                ),
                "priority": "high",
                "risk_level": "high",
                "category": "memory_leak",
                "supporting_evidence": [
                    f"Monotonic slope detected on memory_percent",
                    f"Service risk score: {latest_risk.risk_score if latest_risk else 'N/A'}",
                ],
                "expected_benefit": "Prevents unplanned container termination, downtime, and packet loss.",
                "suggested_action": "Profile memory heaps, inspect connection pool leaks, or perform scheduled container restart.",
            })

        # Check for CPU saturation pattern
        cpu_anom = next((a for a in anomalies if a.metric_name == "cpu_percent" and a.current_value >= 80.0), None)
        cpu_pred = next((p for p in predictions if p.metric_name == "cpu_percent" and p.predicted_value >= 85.0), None)

        if cpu_anom or cpu_pred:
            recommendations_to_create.append({
                "title": f"Pre-emptively Scale Replica Count for {service_name}",
                "description": (
                    f"CPU trend projections indicate {service_name} will exceed 85% compute capacity. "
                    "Proactive horizontal scaling will absorb upcoming traffic without request queueing."
                ),
                "priority": "medium",
                "risk_level": "medium",
                "category": "capacity_growth",
                "supporting_evidence": [
                    f"Projected CPU breach: {cpu_pred.predicted_value if cpu_pred else cpu_anom.current_value}%",
                    "Traffic trajectory shows sustained upward trend",
                ],
                "expected_benefit": "Eliminates P95 latency spikes and prevents request throttling under peak load.",
                "suggested_action": "Increase deployment replica count from current level or adjust HPA thresholds.",
            })

        # Check for high flapping frequency or repeated failures
        if latest_risk and latest_risk.failed_recoveries_count > 0:
            recommendations_to_create.append({
                "title": f"Audit Automated Recovery Handlers for {service_name}",
                "description": (
                    f"Automated recovery actions have failed {latest_risk.failed_recoveries_count} times recently on {service_name}. "
                    "Service may require deeper configuration fixes rather than restart actions."
                ),
                "priority": "critical",
                "risk_level": "critical",
                "category": "flapping_policy",
                "supporting_evidence": [
                    f"Failed automated recovery attempts: {latest_risk.failed_recoveries_count}",
                    f"Overall service health risk: {latest_risk.risk_category} ({latest_risk.risk_score}/100)",
                ],
                "expected_benefit": "Restores automated remediation reliability and reduces manual operator on-call burden.",
                "suggested_action": "Review container logs for underlying crash reasons and verify environment variable integrity.",
            })

        # Persist unique recommendations
        created_records: List[PreventiveRecommendation] = []
        for rec in recommendations_to_create:
            # Check for existing open recommendation with same title and service
            dup_q = select(PreventiveRecommendation).where(
                and_(
                    PreventiveRecommendation.organization_id == organization_id,
                    PreventiveRecommendation.service_id == service_id,
                    PreventiveRecommendation.title == rec["title"],
                    PreventiveRecommendation.status == "open",
                )
            )
            dup_res = await db.execute(dup_q)
            if dup_res.scalars().first():
                continue

            record = PreventiveRecommendation(
                organization_id=organization_id,
                service_id=service_id,
                service_name=service_name,
                title=rec["title"],
                description=rec["description"],
                priority=rec["priority"],
                risk_level=rec["risk_level"],
                category=rec["category"],
                supporting_evidence_json=json.dumps(rec["supporting_evidence"]),
                expected_benefit=rec["expected_benefit"],
                suggested_action=rec["suggested_action"],
                status="open",
                created_at=utc_now(),
            )
            db.add(record)
            created_records.append(record)

        if created_records:
            await db.flush()

        return created_records
