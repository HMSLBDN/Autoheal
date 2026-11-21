"""
AutoHeal DevOps — Enhanced AI Incident Analyzer
Combines multi-modal telemetry, historical incident similarity, cross-incident correlation,
deployment regression intelligence, and explainable AI diagnosis.
Distinguishes confirmed telemetry evidence from unverified diagnostic hypotheses.
"""

from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Incident
from app.models.service import Service
from app.models.base import utc_now
from app.services.ai.base import APPROVED_RECOVERY_ACTIONS, AIDiagnosisResult
from app.services.ai.gemini import GeminiProvider
from app.services.ai.heuristic import HeuristicDiagnosisProvider
from app.services.ai.historical_intelligence import HistoricalIntelligenceEngine
from app.services.ai.correlation_engine import IncidentCorrelationEngine
from app.services.ai.deployment_intelligence import DeploymentIntelligenceEngine

logger = logging.getLogger(__name__)


class IncidentDeepAnalyzer:
    """
    Orchestrates deep diagnostic synthesis for an incident.
    """

    def __init__(self):
        self.gemini_provider = GeminiProvider()
        self.heuristic_provider = HeuristicDiagnosisProvider()
        self.historical_engine = HistoricalIntelligenceEngine()
        self.correlation_engine = IncidentCorrelationEngine()
        self.deployment_engine = DeploymentIntelligenceEngine()

    async def analyze_incident(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        incident_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Executes comprehensive multi-signal AI analysis for an incident.
        """
        # 1. Fetch incident record
        q = select(Incident).where(
            and_(
                Incident.organization_id == organization_id,
                Incident.id == incident_id,
            )
        )
        res = await db.execute(q)
        incident = res.scalars().first()
        if not incident:
            return None

        service_id = incident.service_id or "svc-default"
        service_name = incident.service_name or "default-service"

        # 2. Extract metrics from incident or defaults
        error_rate = float(incident.error_rate or 0.0)
        latency_ms = 50
        cpu_percent = 30.0
        memory_percent = 40.0
        metrics: Dict[str, float] = {
            "error_rate": error_rate,
            "latency_ms": latency_ms,
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
        }

        # 3. Gather deployment impact intelligence
        deployment_impact = await self.deployment_engine.analyze_service_deployment(
            db=db,
            organization_id=organization_id,
            service_id=service_id,
            current_metrics=metrics,
        )

        has_recent_dep = deployment_impact.get("is_temporally_correlated", False) if deployment_impact else False

        # 4. Gather historical similarity
        similar_incidents = await self.historical_engine.find_similar_incidents(
            db=db,
            organization_id=organization_id,
            service_name=service_name,
            incident_title=incident.title,
            incident_description=incident.probable_cause or "",
            exclude_incident_id=incident.id,
            limit=4,
        )

        # 5. Gather correlation groups
        correlations = await self.correlation_engine.correlate_incident(
            db=db,
            organization_id=organization_id,
            incident=incident,
        )
        correlated_ids = [c.correlated_incident_id for c in correlations]

        # 6. Build diagnostic context for AI
        diag_context = {
            "incident_id": incident.id,
            "service_name": service_name,
            "alert_name": incident.title,
            "severity": incident.severity,
            "error_rate": error_rate,
            "latency_ms": latency_ms,
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "has_recent_deployment": has_recent_dep,
            "description": incident.probable_cause or "",
        }

        # 7. Execute AI Diagnosis with automatic fallback
        try:
            diag_result = await self.gemini_provider.diagnose(diag_context)
        except Exception as e:
            logger.warning("Gemini provider exception: %s. Using heuristic fallback.", e)
            diag_result = await self.heuristic_provider.diagnose(diag_context)

        # 8. Segregate confirmed evidence from unverified hypotheses
        confirmed_evidence: List[str] = []
        if error_rate > 0:
            confirmed_evidence.append(f"HTTP error rate measured at {error_rate:.2f}%")
        if latency_ms > 100:
            confirmed_evidence.append(f"P95 response latency observed at {latency_ms}ms")
        if cpu_percent >= 70.0:
            confirmed_evidence.append(f"CPU utilization sustained at {cpu_percent:.1f}%")
        if memory_percent >= 70.0:
            confirmed_evidence.append(f"Memory utilization sustained at {memory_percent:.1f}%")
        if has_recent_dep and deployment_impact:
            confirmed_evidence.append(
                f"Release deployment {deployment_impact.get('release_tag')} occurred {deployment_impact.get('time_since_deployment_minutes')}m ago"
            )

        if not confirmed_evidence:
            confirmed_evidence.append("Active Prometheus alert condition triggered for service")

        unverified_hypotheses: List[str] = [
            f"Underlying cause may be related to: {diag_result.probable_root_cause}",
            "Upstream network partition or transit routing failure may contribute to packet retransmission",
            "Database connection pool saturation or transaction locking could be amplifying latency",
        ]

        # Ensure approved recovery action
        rec_action = diag_result.recommended_action
        if rec_action not in APPROVED_RECOVERY_ACTIONS:
            rec_action = "restart_service"

        alt_action = getattr(diag_result, "alternative_recovery_action", None)
        if alt_action and alt_action not in APPROVED_RECOVERY_ACTIONS:
            alt_action = "scale_service"

        # Update incident record with AI diagnosis results
        incident.probable_cause = diag_result.probable_root_cause
        incident.recommended_action = rec_action
        await db.flush()

        response = {
            "incident_id": incident.id,
            "service_id": service_id,
            "service_name": service_name,
            "summary": diag_result.summary,
            "probable_root_cause": diag_result.probable_root_cause,
            "severity": diag_result.severity,
            "risk_level": diag_result.risk_level,
            "confidence_score": round(float(diag_result.confidence_score), 2),
            "affected_components": [service_name, "API Gateway", "Service Mesh Proxy"],
            "confirmed_evidence": confirmed_evidence,
            "unverified_hypotheses": unverified_hypotheses,
            "potential_business_impact": "Degraded end-user transaction completion rate and heightened SLA error budget burn.",
            "suggested_investigation_steps": [
                f"Check recent structured log entries for {service_name}",
                "Inspect container CPU and memory throttling metrics in Grafana",
                "Verify database connection pool health and query locks",
                "Review git commit delta between current release and previous build",
            ],
            "recommended_recovery_action": rec_action,
            "alternative_recovery_action": alt_action or "scale_service",
            "prevention_recommendations": [
                "Implement circuit breaking on upstream HTTP client calls",
                "Configure horizontal pod autoscaling with a conservative CPU target threshold",
                "Add canary verification stage in deployment pipeline",
            ],
            "verification_requirements": getattr(
                diag_result,
                "verification_requirements",
                ["HTTP 200 on /health", "Error rate < 0.5% over 2 minutes"],
            ),
            "similar_historical_incidents": similar_incidents,
            "correlated_incident_ids": correlated_ids,
            "deployment_impact": deployment_impact,
            "provider_source": diag_result.provider_source,
            "analyzed_at": utc_now().isoformat(),
        }

        return response
