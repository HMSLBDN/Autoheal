"""
AutoHeal DevOps — Alertmanager Ingestion Webhook & Incident Detection Router
Validates incoming Prometheus/Alertmanager webhook alerts, verifies HMAC signatures,
deduplicates firing alerts, creates/updates incidents, and triggers AI diagnosis.
"""

from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Set
import uuid
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import DatabaseDep, WebhookAuthDep
from app.models.audit import AuditLog
from app.models.incident import Incident, IncidentEvent, IncidentEvidence, IncidentTransition
from app.models.service import Service
from app.schemas.alert import AlertmanagerWebhookPayload, AlertWebhookResponse
from app.services.ai.factory import get_ai_provider
from app.services.events import event_broadcaster

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["Alerts & Monitoring"])

ACTIVE_INCIDENT_STATUSES = ["open", "investigating", "recovering", "escalated"]

SEVERITY_RANK = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}


def _map_severity(raw: Optional[str]) -> str:
    """Normalizes Alertmanager severity into AutoHeal severity schema."""
    if not raw:
        return "high"
    val = raw.lower().strip()
    if val in ("critical", "page", "fatal"):
        return "critical"
    if val in ("high", "warning", "warn"):
        return "high"
    if val in ("medium", "moderate"):
        return "medium"
    return "low"


async def _generate_unique_incident_id(db: DatabaseDep, session_created_ids: Set[str]) -> str:
    """
    Generates a guaranteed collision-free incident ID.
    Avoids primary key collisions across both committed DB rows and uncommitted session rows.
    """
    stmt = select(Incident.id)
    res = await db.execute(stmt)
    existing_ids = set(res.scalars().all()) | session_created_ids

    candidate_num = len(existing_ids) + 1001
    while f"INC-{candidate_num}" in existing_ids:
        candidate_num += 1

    new_id = f"INC-{candidate_num}"
    session_created_ids.add(new_id)
    return new_id


@router.post(
    "/webhook",
    response_model=AlertWebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest Alertmanager webhook alerts",
)
async def alertmanager_webhook(
    payload: AlertmanagerWebhookPayload,
    authorized: WebhookAuthDep,
    db: DatabaseDep,
) -> AlertWebhookResponse:
    """
    Secure Alertmanager webhook endpoint.
    Requires HMAC signature (X-AutoHeal-Signature) or Alertmanager secret.
    Parses firing and resolved alerts, prevents duplicate incidents,
    and enriches new incidents with automated AI diagnosis.
    """
    alerts = payload.alerts
    if not alerts:
        return AlertWebhookResponse(
            status="success",
            processed_alerts=0,
            incidents_created=0,
            incidents_updated=0,
            details=["Payload contained no active alerts."],
        )

    incidents_created = 0
    incidents_updated = 0
    details: List[str] = []
    now = datetime.now(timezone.utc)
    ai_provider = get_ai_provider()

    # In-memory tracking for intra-batch deduplication and collision-free ID allocation
    session_incidents_by_service: Dict[str, Incident] = {}
    session_created_ids: Set[str] = set()

    for alert in alerts:
        alertname = alert.labels.alertname or "UnknownAlert"

        # 1. Determine affected service name
        svc_name = (
            alert.labels.service
            or alert.labels.job
            or payload.commonLabels.get("service")
            or payload.commonLabels.get("job")
            or None
        )

        # 2. Look up Service in DB (by name or by ID)
        service = None
        if svc_name:
            svc_stmt = (
                select(Service)
                .where(or_(Service.name == svc_name, Service.id == svc_name))
                .with_for_update()
            )
            svc_res = await db.execute(svc_stmt)
            service = svc_res.scalars().first()

        if not service:
            if not svc_name:
                # Fallback to default or first available active service when no label provided
                fallback_res = await db.execute(select(Service).limit(1))
                service = fallback_res.scalars().first()

        if not service:
            details.append(f"Skipped alert '{alertname}': No provisioned service matching '{svc_name or 'unspecified'}'.")
            continue

        mapped_sev = _map_severity(alert.labels.severity)

        # 3. Check for existing active incident on this service (intra-batch map first, then DB)
        existing_incident = session_incidents_by_service.get(service.id)
        if existing_incident is None or existing_incident.status not in ACTIVE_INCIDENT_STATUSES:
            active_inc_stmt = (
                select(Incident)
                .where(
                    Incident.service_id == service.id,
                    Incident.status.in_(ACTIVE_INCIDENT_STATUSES),
                )
                .order_by(desc(Incident.created_at))
            )
            active_inc_res = await db.execute(active_inc_stmt)
            existing_incident = active_inc_res.scalars().first()
            if existing_incident:
                session_incidents_by_service[service.id] = existing_incident

        # 4. Handle RESOLVED alerts
        if alert.status == "resolved":
            if existing_incident and existing_incident.status in ACTIVE_INCIDENT_STATUSES:
                prev_status = existing_incident.status
                existing_incident.status = "resolved"
                existing_incident.recovery_status = "Resolved by Alertmanager"
                existing_incident.resolved_at = now
                existing_incident.updated_at = now

                # Add timeline event
                db.add(IncidentEvent(
                    incident_id=existing_incident.id,
                    label="Alert Resolved",
                    detail=f"Prometheus alert '{alertname}' marked resolved. Normalizing telemetry.",
                    timestamp=now,
                    tone="success",
                ))

                # Add state transition record
                db.add(IncidentTransition(
                    id=uuid.uuid4(),
                    organization_id=service.organization_id,
                    incident_id=existing_incident.id,
                    actor_id=None,
                    actor_email="alertmanager@autoheal.internal",
                    actor_role="system",
                    previous_state=prev_status,
                    new_state="resolved",
                    reason=f"Prometheus alert '{alertname}' resolved in Alertmanager.",
                    evidence_id=None,
                    sign_off=False,
                    created_at=now,
                ))

                # Add audit log
                db.add(AuditLog(
                    organization_id=service.organization_id,
                    action="incident_resolved_by_alertmanager",
                    resource_type="incident",
                    resource_id=existing_incident.id,
                    details=f"Incident '{existing_incident.id}' auto-resolved via Alertmanager webhook.",
                ))
                incidents_updated += 1
                details.append(f"Resolved incident '{existing_incident.id}' for service '{service.name}'.")
                await event_broadcaster.broadcast(service.organization_id, "incident_updated", {
                    "id": existing_incident.id,
                    "status": "resolved",
                    "recoveryStatus": "Resolved by alert resolution",
                })
            else:
                details.append(f"Received resolved alert for '{service.name}', but no active incident existed.")
            continue

        # 5. Handle FIRING alerts
        if existing_incident and existing_incident.status in ACTIVE_INCIDENT_STATUSES:
            # DEDUPLICATION: Alert is already being tracked; update existing incident
            existing_incident.updated_at = now
            if SEVERITY_RANK.get(mapped_sev, 0) > SEVERITY_RANK.get(existing_incident.severity, 0):
                existing_incident.severity = mapped_sev

            detail_text = alert.annotations.description or f"Prometheus alert '{alertname}' reaffirmed breach."

            # Append timeline event
            db.add(IncidentEvent(
                incident_id=existing_incident.id,
                label="Alert Re-triggered",
                detail=detail_text,
                timestamp=now,
                tone="warning",
            ))

            # Append refreshed telemetry evidence
            db.add(IncidentEvidence(
                incident_id=existing_incident.id,
                kind="metric",
                title=alertname,
                detail=f"Breach reaffirmed: {detail_text}",
                timestamp=now,
            ))

            incidents_updated += 1
            details.append(f"Deduplicated alert '{alertname}' -> Updated existing incident '{existing_incident.id}'.")
            await event_broadcaster.broadcast(service.organization_id, "incident_updated", {
                "id": existing_incident.id,
                "status": existing_incident.status,
                "severity": existing_incident.severity,
            })

        else:
            # CREATE NEW INCIDENT
            incident_id = await _generate_unique_incident_id(db, session_created_ids)

            title = alert.annotations.summary or f"Telemetry Alert: {alertname}"
            description = alert.annotations.description or f"Alertmanager alert '{alertname}' triggered."

            new_incident = Incident(
                id=incident_id,
                organization_id=service.organization_id,
                service_id=service.id,
                service_name=service.name,
                title=title,
                severity=mapped_sev,
                status="open",
                detected_at=now,
                recovery_status="AI diagnosis in progress",
                error_rate=service.error_rate or 2.15,
                threshold=1.0,
                probable_cause="Awaiting AI root cause analysis",
                recommended_action="restart_service",
            )
            db.add(new_incident)
            await db.flush()

            # Cache in session tracking map
            session_incidents_by_service[service.id] = new_incident

            # Attach initial telemetry evidence
            db.add(IncidentEvidence(
                incident_id=new_incident.id,
                kind="metric",
                title=alertname,
                detail=description,
                timestamp=now,
            ))

            # Attach initial detection event
            db.add(IncidentEvent(
                incident_id=new_incident.id,
                label="Incident Detected",
                detail=description,
                timestamp=now,
                tone="warning",
            ))

            # Record initial lifecycle transition
            db.add(IncidentTransition(
                id=uuid.uuid4(),
                organization_id=service.organization_id,
                incident_id=new_incident.id,
                actor_id=None,
                actor_email="alertmanager@autoheal.internal",
                actor_role="system",
                previous_state="none",
                new_state="open",
                reason=f"Prometheus alert '{alertname}' triggered incident creation.",
                evidence_id=None,
                sign_off=False,
                created_at=now,
            ))

            # Run AI Root Cause Diagnosis
            diag_context = {
                "service_name": service.name,
                "alert_name": alertname,
                "severity": mapped_sev,
                "error_rate": new_incident.error_rate,
                "latency_ms": service.latency_ms,
                "description": description,
                "probable_cause": alert.annotations.probable_cause,
            }
            try:
                diagnosis = await ai_provider.diagnose(diag_context)
                new_incident.probable_cause = diagnosis.probable_root_cause
                new_incident.recommended_action = diagnosis.recommended_action
                new_incident.recovery_status = "Approval required"

                db.add(IncidentEvidence(
                    incident_id=new_incident.id,
                    kind="log",
                    title="AI Root Cause Analysis",
                    detail=f"{diagnosis.probable_root_cause} (Risk: {diagnosis.risk_level})",
                    timestamp=now,
                ))

                db.add(IncidentEvent(
                    incident_id=new_incident.id,
                    label="AI Diagnosis Generated",
                    detail=f"Recommended: {diagnosis.recommended_action} (Confidence: {int(diagnosis.confidence_score * 100)}%)",
                    timestamp=now,
                    tone="neutral",
                ))
            except Exception as e:
                logger.warning("AI diagnosis execution encountered an error: %s", e)
                new_incident.probable_cause = "Automated heuristic analysis pending"
                new_incident.recovery_status = "Approval required"

            # Record audit log
            db.add(AuditLog(
                organization_id=service.organization_id,
                action="incident_created_by_alertmanager",
                resource_type="incident",
                resource_id=new_incident.id,
                details=f"Created incident '{new_incident.id}' for service '{service.name}' with severity '{mapped_sev}'.",
            ))

            incidents_created += 1
            details.append(f"Created incident '{new_incident.id}' with AI recommended action '{new_incident.recommended_action}'.")
            await event_broadcaster.broadcast(service.organization_id, "incident_created", {
                "id": new_incident.id,
                "title": new_incident.title,
                "serviceName": new_incident.service_name,
                "severity": new_incident.severity,
                "status": new_incident.status,
            })

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("Failed to commit Alertmanager webhook transaction: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database transaction failure during alert processing: {str(exc)}",
        )

    return AlertWebhookResponse(
        status="success",
        processed_alerts=len(alerts),
        incidents_created=incidents_created,
        incidents_updated=incidents_updated,
        details=details,
    )
