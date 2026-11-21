"""
AutoHeal DevOps — Unified Operations Timeline Service
Aggregates and orders operational events chronologically:
Deployments, Alerts, Incidents, AI Diagnoses, Operator Decisions, Recovery Attempts,
Verifications, Notifications, and Resolution Events.
"""

from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Incident
from app.models.recovery import RecoveryAction
from app.models.service import DeploymentEvent, Service
from app.models.enterprise import (
    NotificationDelivery,
    EscalationEvent,
    ReleaseEvaluation,
    IncidentComment,
)
from app.schemas.enterprise import TimelineItemResponse, UnifiedTimelineResponse

logger = logging.getLogger(__name__)


class UnifiedTimelineService:
    """
    Constructs a unified, organization-scoped chronological timeline.
    """

    async def get_timeline(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        service_id: Optional[str] = None,
        limit: int = 50,
    ) -> UnifiedTimelineResponse:
        """Queries and aggregates events across multiple models."""
        timeline_items: List[TimelineItemResponse] = []

        # 1. Incidents
        inc_q = select(Incident).where(Incident.organization_id == organization_id)
        if service_id:
            inc_q = inc_q.where(Incident.service_id == service_id)
        inc_q = inc_q.order_by(desc(Incident.detected_at)).limit(limit)
        inc_res = await db.execute(inc_q)
        for inc in inc_res.scalars().all():
            timeline_items.append(
                TimelineItemResponse(
                    id=f"inc-{inc.id}",
                    category="incident",
                    title=f"Incident Detected: {inc.title}",
                    detail=f"Status: {inc.status} · Severity: {inc.severity} · Error rate: {inc.error_rate}%",
                    service_name=inc.service_name,
                    severity=inc.severity,
                    status=inc.status,
                    timestamp=inc.detected_at.isoformat() if inc.detected_at else "",
                    metadata={"incident_id": inc.id, "probable_cause": inc.probable_cause},
                )
            )

        # 2. Deployments
        dep_q = (
            select(DeploymentEvent, Service.name)
            .join(Service, Service.id == DeploymentEvent.service_id)
            .where(Service.organization_id == organization_id)
        )
        if service_id:
            dep_q = dep_q.where(DeploymentEvent.service_id == service_id)
        dep_q = dep_q.order_by(desc(DeploymentEvent.deployed_at)).limit(limit)
        dep_res = await db.execute(dep_q)
        for dep, svc_name in dep_res.all():
            timeline_items.append(
                TimelineItemResponse(
                    id=f"dep-{dep.id}",
                    category="deployment",
                    title=f"Release Deployed: {dep.release_tag}",
                    detail=f"Deployed by {dep.deployed_by} (status: {dep.status})",
                    service_name=svc_name,
                    status=dep.status,
                    timestamp=dep.deployed_at.isoformat() if dep.deployed_at else "",
                    metadata={"commit_sha": dep.commit_sha, "release_tag": dep.release_tag},
                )
            )

        # 3. Recoveries
        rec_q = (
            select(RecoveryAction)
            .join(Incident, Incident.id == RecoveryAction.incident_id)
            .where(Incident.organization_id == organization_id)
        )
        if service_id:
            rec_q = rec_q.where(RecoveryAction.service_id == service_id)
        rec_q = rec_q.order_by(desc(RecoveryAction.requested_at)).limit(limit)
        rec_res = await db.execute(rec_q)
        for rec in rec_res.scalars().all():
            timeline_items.append(
                TimelineItemResponse(
                    id=f"rec-{rec.id}",
                    category="recovery",
                    title=f"Recovery Action: {rec.action}",
                    detail=f"Status: {rec.status} · Verification: {rec.verification} · Requested by {rec.requested_by}",
                    service_name=rec.service_name,
                    status=rec.status,
                    timestamp=rec.requested_at.isoformat() if rec.requested_at else "",
                    metadata={"incident_id": rec.incident_id, "duration_seconds": rec.duration_seconds},
                )
            )

        # 4. Notifications
        notif_q = select(NotificationDelivery).where(NotificationDelivery.organization_id == organization_id)
        notif_q = notif_q.order_by(desc(NotificationDelivery.created_at)).limit(limit)
        notif_res = await db.execute(notif_q)
        for notif in notif_res.scalars().all():
            timeline_items.append(
                TimelineItemResponse(
                    id=f"notif-{notif.id}",
                    category="notification",
                    title=f"Notification Dispatched ({notif.event_type})",
                    detail=f"Status: {notif.status} · Retries: {notif.retry_count}/{notif.max_retries}",
                    status=notif.status,
                    timestamp=notif.created_at.isoformat() if notif.created_at else "",
                    metadata={"channel_id": str(notif.channel_id), "event_type": notif.event_type},
                )
            )

        # 5. Escalation Events
        esc_q = select(EscalationEvent).where(EscalationEvent.organization_id == organization_id)
        esc_q = esc_q.order_by(desc(EscalationEvent.escalated_at)).limit(limit)
        esc_res = await db.execute(esc_q)
        for esc in esc_res.scalars().all():
            timeline_items.append(
                TimelineItemResponse(
                    id=f"esc-{esc.id}",
                    category="escalation",
                    title=f"Escalation Level {esc.escalation_level}",
                    detail=f"{esc.action_taken} — {esc.trigger_reason}",
                    timestamp=esc.escalated_at.isoformat() if esc.escalated_at else "",
                    metadata={"incident_id": esc.incident_id, "level": esc.escalation_level},
                )
            )

        # Sort all aggregated items descending by timestamp
        timeline_items.sort(key=lambda item: item.timestamp, reverse=True)
        paged_items = timeline_items[:limit]

        return UnifiedTimelineResponse(
            total_events=len(timeline_items),
            items=paged_items,
        )
