"""
AutoHeal DevOps — Alertmanager Ingestion Webhook & Incident Detection Router
Validates incoming Prometheus/Alertmanager webhook alerts, verifies HMAC signatures,
deduplicates firing alerts, creates/updates incidents, and triggers AI diagnosis.
"""

from datetime import datetime, timezone
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from app.api.deps import DatabaseDep, WebhookAuthDep
from app.models.audit import AuditLog
from app.models.incident import Incident, IncidentEvent, IncidentEvidence
from app.models.service import Service
from app.schemas.alert import AlertmanagerWebhookPayload, AlertWebhookResponse
from app.services.ai.factory import get_ai_provider
from app.services.events import event_broadcaster

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["Alerts & Monitoring"])


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

    for alert in alerts:
        # 1. Determine affected service name
        svc_name = (
            alert.labels.service
            or alert.labels.job
            or payload.commonLabels.get("service")
            or payload.commonLabels.get("job")
            or "checkout-api"
        )

        # 2. Look up Service in DB
        svc_stmt = select(Service).where(Service.name == svc_name)
        svc_res = await db.execute(svc_stmt)
        service = svc_res.scalars().first()

        if not service:
            # Fallback to first available active service
            fallback_res = await db.execute(select(Service).limit(1))
            service = fallback_res.scalars().first()

        if not service:
            details.append(f"Skipped alert '{alert.labels.alertname}': No provisioned service matching '{svc_name}'.")
            continue

        mapped_sev = _map_severity(alert.labels.severity)

        # 3. Check for existing active incident on this service
        active_inc_stmt = (
            select(Incident)
            .where(
                Incident.service_id == service.id,
                Incident.status.in_(["open", "investigating", "recovering"]),
            )
            .order_by(desc(Incident.created_at))
        )
        active_inc_res = await db.execute(active_inc_stmt)
        existing_incident = active_inc_res.scalars().first()

        # 4. Handle RESOLVED alerts
        if alert.status == "resolved":
            if existing_incident:
                existing_incident.status = "resolved"
                existing_incident.recovery_status = "Resolved by Alertmanager"
                existing_incident.resolved_at = now

                db.add(IncidentEvent(
                    incident_id=existing_incident.id,
                    label="Alert Resolved",
                    detail=f"Prometheus alert '{alert.labels.alertname}' marked resolved. Normalizing telemetry.",
                    timestamp=now,
                    tone="success",
                ))

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
        if existing_incident:
            # DEDUPLICATION: Alert is already being tracked; update existing incident
            existing_incident.updated_at = now
            if mapped_sev == "critical" and existing_incident.severity != "critical":
                existing_incident.severity = "critical"

            db.add(IncidentEvent(
                incident_id=existing_incident.id,
                label="Alert Re-triggered",
                detail=alert.annotations.description or f"Prometheus alert '{alert.labels.alertname}' reaffirmed breach.",
                timestamp=now,
                tone="warning",
            ))
            incidents_updated += 1
            details.append(f"Deduplicated alert '{alert.labels.alertname}' -> Updated existing incident '{existing_incident.id}'.")
            await event_broadcaster.broadcast(service.organization_id, "incident_updated", {
                "id": existing_incident.id,
                "status": existing_incident.status,
                "severity": existing_incident.severity,
            })

        else:
            # CREATE NEW INCIDENT
            all_inc_stmt = select(Incident)
            all_inc_res = await db.execute(all_inc_stmt)
            count = len(all_inc_res.scalars().all()) + 1001
            incident_id = f"INC-{count}"

            title = alert.annotations.summary or f"Telemetry Alert: {alert.labels.alertname}"
            description = alert.annotations.description or f"Alertmanager alert '{alert.labels.alertname}' triggered."

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

            # Attach initial telemetry evidence
            db.add(IncidentEvidence(
                incident_id=new_incident.id,
                kind="metric",
                title=alert.labels.alertname,
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

            # Run AI Root Cause Diagnosis
            diag_context = {
                "service_name": service.name,
                "alert_name": alert.labels.alertname,
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

    await db.commit()

    return AlertWebhookResponse(
        status="success",
        processed_alerts=len(alerts),
        incidents_created=incidents_created,
        incidents_updated=incidents_updated,
        details=details,
    )
