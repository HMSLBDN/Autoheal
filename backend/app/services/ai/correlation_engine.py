"""
AutoHeal DevOps — Cross-Incident Root Cause Correlation Engine
Identifies cascading failures and correlates concurrent incidents within an organization
based on temporal proximity, shared services, and release deployments.
Maintains clear correlation groups without automatically merging incidents.
"""

from datetime import datetime, timedelta
import json
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Incident
from app.models.intelligence import IncidentCorrelation
from app.models.service import Service, DeploymentEvent
from app.models.base import utc_now


class IncidentCorrelationEngine:
    """
    Correlates concurrent incidents to identify shared root causes (e.g. shared database bottleneck,
    failed deployment cascading to multiple dependent services).
    """

    CORRELATION_WINDOW_MINUTES = 20

    async def correlate_incident(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        incident: Incident,
    ) -> List[IncidentCorrelation]:
        """
        Evaluates an incident against other open or recently triggered incidents in the organization.
        Creates IncidentCorrelation records if temporal, architectural, or deployment links are found.
        """
        inc_time = getattr(incident, "detected_at", None) or getattr(incident, "created_at", None) or utc_now()
        window_start = inc_time - timedelta(minutes=self.CORRELATION_WINDOW_MINUTES)
        window_end = inc_time + timedelta(minutes=self.CORRELATION_WINDOW_MINUTES)

        # Query concurrent incidents within the correlation window
        query = select(Incident).where(
            and_(
                Incident.organization_id == organization_id,
                Incident.id != incident.id,
                Incident.detected_at >= window_start,
                Incident.detected_at <= window_end,
            )
        ).order_by(Incident.detected_at)

        result = await db.execute(query)
        concurrent_incidents = result.scalars().all()

        if not concurrent_incidents:
            return []

        # Check for recent deployment within 60 minutes
        dep_start = inc_time - timedelta(minutes=60)
        dep_query = (
            select(DeploymentEvent)
            .join(Service, Service.id == DeploymentEvent.service_id)
            .where(
                and_(
                    Service.organization_id == organization_id,
                    DeploymentEvent.deployed_at >= dep_start,
                    DeploymentEvent.deployed_at <= inc_time,
                )
            )
            .order_by(desc(DeploymentEvent.deployed_at))
        )
        dep_res = await db.execute(dep_query)
        recent_deployment = dep_res.scalars().first()

        created_correlations: List[IncidentCorrelation] = []

        for other in concurrent_incidents:
            # Check if correlation already exists
            existing_query = select(IncidentCorrelation).where(
                and_(
                    IncidentCorrelation.organization_id == organization_id,
                    (
                        (IncidentCorrelation.primary_incident_id == incident.id)
                        & (IncidentCorrelation.correlated_incident_id == other.id)
                    )
                    | (
                        (IncidentCorrelation.primary_incident_id == other.id)
                        & (IncidentCorrelation.correlated_incident_id == incident.id)
                    ),
                )
            )
            existing_res = await db.execute(existing_query)
            if existing_res.scalars().first():
                continue

            # Determine correlation factors
            shared_service = (incident.service_id == other.service_id)
            other_time = getattr(other, "detected_at", None) or getattr(other, "created_at", None) or inc_time
            time_diff_sec = abs((inc_time - other_time).total_seconds())

            shared_evidence = [
                f"Both incidents occurred within {int(time_diff_sec / 60)} minutes of each other"
            ]

            correlation_score = 0.5
            correlation_type = "temporal"

            if shared_service:
                correlation_score += 0.3
                correlation_type = "shared_service"
                shared_evidence.append(f"Both incidents affect the same service: {incident.service_name}")

            if recent_deployment:
                correlation_score += 0.2
                correlation_type = "deployment_impact"
                shared_evidence.append(
                    f"Correlated release deployment {recent_deployment.release_tag} completed shortly before triggers"
                )

            correlation_score = min(0.99, correlation_score)

            # Generate group identifier (deterministic based on earliest incident)
            earliest_id = min(incident.id, other.id)
            group_id = f"corr-group-{earliest_id[:8]}"

            explanation = (
                f"Detected cascading or concurrent failure pattern between {incident.service_name} "
                f"({incident.title}) and {other.service_name} ({other.title}). Shared root cause likely."
            )

            correlation = IncidentCorrelation(
                organization_id=organization_id,
                correlation_group_id=group_id,
                primary_incident_id=incident.id,
                correlated_incident_id=other.id,
                correlation_score=round(correlation_score, 2),
                correlation_type=correlation_type,
                shared_evidence_json=json.dumps(shared_evidence),
                explanation=explanation,
                created_at=utc_now(),
            )
            db.add(correlation)
            created_correlations.append(correlation)

        if created_correlations:
            await db.flush()

        return created_correlations

    async def get_correlation_groups(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        incident_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves formatted correlation groups for an organization or for a specific incident.
        """
        query = select(IncidentCorrelation).where(
            IncidentCorrelation.organization_id == organization_id
        )
        if incident_id:
            query = query.where(
                (IncidentCorrelation.primary_incident_id == incident_id)
                | (IncidentCorrelation.correlated_incident_id == incident_id)
            )

        query = query.order_by(desc(IncidentCorrelation.created_at))
        result = await db.execute(query)
        correlations = result.scalars().all()

        # Group by correlation_group_id
        groups_dict: Dict[str, Dict[str, Any]] = {}

        for corr in correlations:
            gid = corr.correlation_group_id
            if gid not in groups_dict:
                # Load primary and correlated incidents
                prim_q = select(Incident).where(Incident.id == corr.primary_incident_id)
                prim_res = await db.execute(prim_q)
                prim = prim_res.scalars().first()

                groups_dict[gid] = {
                    "group_id": gid,
                    "primary_incident_id": corr.primary_incident_id,
                    "correlation_type": corr.correlation_type,
                    "correlation_score": corr.correlation_score,
                    "explanation": corr.explanation,
                    "shared_evidence": json.loads(corr.shared_evidence_json or "[]"),
                    "incidents": [],
                    "created_at": corr.created_at.isoformat() if corr.created_at else "",
                }

            # Add correlated incident to group
            corr_q = select(Incident).where(Incident.id == corr.correlated_incident_id)
            corr_res = await db.execute(corr_q)
            c_inc = corr_res.scalars().first()
            if c_inc:
                # Check not already present
                existing_ids = [item["incident_id"] for item in groups_dict[gid]["incidents"]]
                if c_inc.id not in existing_ids:
                    groups_dict[gid]["incidents"].append({
                        "incident_id": c_inc.id,
                        "service_name": c_inc.service_name or "unknown",
                        "title": c_inc.title,
                        "severity": c_inc.severity,
                        "status": c_inc.status,
                        "detected_at": c_inc.created_at.isoformat() if c_inc.created_at else "",
                    })

        return list(groups_dict.values())
