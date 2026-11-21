"""
AutoHeal DevOps — Service Health Risk Scorer
Computes explainable 0-100 composite health risk scores from multi-signal telemetry:
error rates, P95 latencies, CPU/memory trends, availability, recovery failure history,
and recent release deployment correlations.
"""

from datetime import datetime, timedelta
import json
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence import ServiceRiskScore
from app.models.incident import Incident
from app.models.service import Service, DeploymentEvent
from app.models.base import utc_now


class ServiceRiskScorer:
    """
    Transparent, explainable risk scoring engine calculating composite health risk (0 to 100).
    Every penalty added is documented as an itemized RiskFactor.
    """

    @staticmethod
    def calculate_score(
        error_rate: float = 0.0,
        latency_ms: float = 50.0,
        cpu_percent: float = 30.0,
        cpu_trend: str = "stable",
        memory_percent: float = 40.0,
        memory_trend: str = "stable",
        availability_pct: float = 99.9,
        failed_recoveries: int = 0,
        recent_deployment: bool = False,
        deployment_error_increase: bool = False,
        incident_frequency_7d: int = 0,
    ) -> Tuple[float, str, List[Dict[str, Any]]]:
        """
        Calculates composite score, category, and list of contributing factors.
        """
        base_score = 10.0
        contributing_factors: List[Dict[str, Any]] = [
            {
                "factor": "Baseline Operating Risk",
                "weight": 10.0,
                "description": "Standard nominal operational risk baseline for running microservices",
                "severity": "low",
            }
        ]

        current_score = base_score

        # 1. Error rate weight: min(30, error_rate * 10)
        if error_rate > 0.0:
            err_weight = min(30.0, error_rate * 10.0)
            severity = "critical" if err_weight >= 20.0 else ("high" if err_weight >= 10.0 else "medium")
            current_score += err_weight
            contributing_factors.append({
                "factor": "HTTP Error Rate",
                "weight": round(err_weight, 1),
                "description": f"Elevated error rate at {error_rate:.2f}% (added {err_weight:.1f} pts)",
                "severity": severity,
            })

        # 2. Latency weight: min(20, (latency_ms / 500) * 20)
        if latency_ms > 100.0:
            lat_weight = min(20.0, (latency_ms / 500.0) * 20.0)
            severity = "critical" if latency_ms >= 500.0 else "medium"
            current_score += lat_weight
            contributing_factors.append({
                "factor": "P95 Response Latency",
                "weight": round(lat_weight, 1),
                "description": f"P95 latency observed at {latency_ms:.1f}ms (added {lat_weight:.1f} pts)",
                "severity": severity,
            })

        # 3. CPU trend: +10 if spiking or > 80%
        if cpu_trend == "spiking" or cpu_percent >= 80.0:
            current_score += 10.0
            contributing_factors.append({
                "factor": "CPU Utilization Strain",
                "weight": 10.0,
                "description": f"CPU utilization critical or rapidly spiking ({cpu_percent:.1f}%, trend: {cpu_trend})",
                "severity": "high",
            })
        elif cpu_percent >= 65.0:
            current_score += 5.0
            contributing_factors.append({
                "factor": "CPU Utilization Warning",
                "weight": 5.0,
                "description": f"CPU utilization elevated ({cpu_percent:.1f}%)",
                "severity": "medium",
            })

        # 4. Memory trend: +15 if leaking or > 85%
        if memory_trend == "leaking" or memory_percent >= 85.0:
            current_score += 15.0
            contributing_factors.append({
                "factor": "Memory Exhaustion / Leak",
                "weight": 15.0,
                "description": f"Memory consumption critical or persistent leak detected ({memory_percent:.1f}%, trend: {memory_trend})",
                "severity": "critical",
            })
        elif memory_percent >= 75.0:
            current_score += 7.0
            contributing_factors.append({
                "factor": "Memory Saturation Warning",
                "weight": 7.0,
                "description": f"Memory utilization high ({memory_percent:.1f}%)",
                "severity": "medium",
            })

        # 5. Availability penalty: max(0, (99.9 - availability) * 10)
        if availability_pct < 99.9:
            avail_penalty = min(20.0, max(0.0, (99.9 - availability_pct) * 10.0))
            if avail_penalty > 0.0:
                current_score += avail_penalty
                contributing_factors.append({
                    "factor": "SLA / Availability Degradation",
                    "weight": round(avail_penalty, 1),
                    "description": f"Availability degraded to {availability_pct:.2f}% below 99.9% target",
                    "severity": "high" if avail_penalty >= 10.0 else "medium",
                })

        # 6. Recent failed recoveries: +10 per failed recovery (max 20)
        if failed_recoveries > 0:
            fail_weight = min(20.0, failed_recoveries * 10.0)
            current_score += fail_weight
            contributing_factors.append({
                "factor": "Failed Automated Recoveries",
                "weight": round(fail_weight, 1),
                "description": f"{failed_recoveries} automated recovery attempts failed in preceding cycle",
                "severity": "critical",
            })

        # 7. Recent deployment regression: +10 if deployment occurred within 2h and error rate increased
        if recent_deployment and (deployment_error_increase or error_rate > 1.0):
            current_score += 10.0
            contributing_factors.append({
                "factor": "Release Deployment Regression",
                "weight": 10.0,
                "description": "Recent deployment temporally correlated with telemetry regression",
                "severity": "high",
            })

        # 8. Incident frequency 7d: +5 if > 3 incidents
        if incident_frequency_7d >= 3:
            freq_weight = min(10.0, (incident_frequency_7d - 2) * 2.5)
            current_score += freq_weight
            contributing_factors.append({
                "factor": "High Incident Flapping Frequency",
                "weight": round(freq_weight, 1),
                "description": f"{incident_frequency_7d} incidents logged for this service in the last 7 days",
                "severity": "medium",
            })

        # Bound score cleanly between 0.0 and 100.0
        final_score = round(max(0.0, min(100.0, current_score)), 1)

        # Categorize
        if final_score <= 30.0:
            category = "low"
        elif final_score <= 60.0:
            category = "moderate"
        elif final_score <= 85.0:
            category = "high"
        else:
            category = "critical"

        return final_score, category, contributing_factors

    async def evaluate_service(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        service_id: str,
        service_name: str,
        current_metrics: Optional[Dict[str, float]] = None,
        cpu_trend: str = "stable",
        memory_trend: str = "stable",
    ) -> ServiceRiskScore:
        """
        Queries DB history for recent incidents, failed recoveries, and deployments,
        computes risk score, and stores/updates ServiceRiskScore.
        """
        metrics = current_metrics or {}
        error_rate = float(metrics.get("error_rate", 0.0))
        latency_ms = float(metrics.get("latency_ms", 45.0))
        cpu_percent = float(metrics.get("cpu_percent", 25.0))
        memory_percent = float(metrics.get("memory_percent", 35.0))
        availability_pct = float(metrics.get("availability_pct", 99.95))

        # Query 7-day incident count for this service
        week_ago = utc_now() - timedelta(days=7)
        inc_count_query = select(func.count(Incident.id)).where(
            and_(
                Incident.organization_id == organization_id,
                Incident.service_id == service_id,
                Incident.created_at >= week_ago,
            )
        )
        inc_count_res = await db.execute(inc_count_query)
        incident_frequency_7d = inc_count_res.scalar_one_or_none() or 0

        # Query recent failed recoveries in last 24 hours
        day_ago = utc_now() - timedelta(days=1)
        failed_rec_query = select(func.count(Incident.id)).where(
            and_(
                Incident.organization_id == organization_id,
                Incident.service_id == service_id,
                Incident.created_at >= day_ago,
                Incident.status == "escalated",
            )
        )
        failed_rec_res = await db.execute(failed_rec_query)
        failed_recoveries = failed_rec_res.scalar_one_or_none() or 0

        # Query recent deployment within last 2 hours
        two_hours_ago = utc_now() - timedelta(hours=2)
        dep_query = (
            select(DeploymentEvent)
            .join(Service, Service.id == DeploymentEvent.service_id)
            .where(
                and_(
                    Service.organization_id == organization_id,
                    DeploymentEvent.service_id == service_id,
                    DeploymentEvent.deployed_at >= two_hours_ago,
                )
            )
            .order_by(desc(DeploymentEvent.deployed_at))
        )
        dep_res = await db.execute(dep_query)
        latest_dep = dep_res.scalars().first()
        recent_deployment = latest_dep is not None
        dep_error_inc = False
        if latest_dep and latest_dep.manifest_summary:
            try:
                m_data = json.loads(latest_dep.manifest_summary)
                if isinstance(m_data, dict):
                    pre_e = float(m_data.get("pre_deployment_error_rate", 0))
                    post_e = float(m_data.get("post_deployment_error_rate", 0))
                    dep_error_inc = post_e > pre_e
            except Exception:
                pass

        score, category, factors = self.calculate_score(
            error_rate=error_rate,
            latency_ms=latency_ms,
            cpu_percent=cpu_percent,
            cpu_trend=cpu_trend,
            memory_percent=memory_percent,
            memory_trend=memory_trend,
            availability_pct=availability_pct,
            failed_recoveries=failed_recoveries,
            recent_deployment=recent_deployment,
            deployment_error_increase=dep_error_inc,
            incident_frequency_7d=incident_frequency_7d,
        )

        risk_record = ServiceRiskScore(
            organization_id=organization_id,
            service_id=service_id,
            service_name=service_name,
            risk_score=score,
            risk_category=category,
            contributing_factors_json=json.dumps(factors),
            cpu_trend=cpu_trend,
            memory_trend=memory_trend,
            incident_frequency_7d=incident_frequency_7d,
            failed_recoveries_count=failed_recoveries,
            recent_deployment_flag=recent_deployment,
            calculated_at=utc_now(),
        )
        db.add(risk_record)
        await db.flush()
        return risk_record
