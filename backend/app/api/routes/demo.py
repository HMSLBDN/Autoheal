"""
AutoHeal DevOps — Safe Demo Controls & Fault Injection Router
Provides authenticated, RBAC-protected controls to trigger controlled microservice failures,
restore services to healthy states, and simulate realistic incident lifecycles.
Strictly disallows arbitrary shell commands or direct Docker socket access.
"""

from datetime import datetime, timezone
import logging
from typing import List, Optional
import uuid
import httpx
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DatabaseDep, OrgDep, RequireOperatorDep
from app.config import get_settings
from app.models.audit import AuditLog
from app.models.incident import Incident, IncidentEvent, IncidentEvidence
from app.models.recovery import RecoveryAction
from app.models.service import Service
from app.schemas.alert import (
    AlertAnnotations,
    AlertItem,
    AlertLabels,
    AlertmanagerWebhookPayload,
)
from app.schemas.demo import (
    DemoFaultRequest,
    DemoFaultResponse,
    DemoResetRequest,
    DemoResetResponse,
    DemoServiceStatus,
    DemoSimulateAlertRequest,
    DemoSimulateAlertResponse,
    DemoStatusResponse,
)
from app.services.ai.factory import get_ai_provider
from app.services.events import event_broadcaster
from app.services.recovery.registry import is_action_allowed, normalize_action

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/demo", tags=["Demo Controls"])

# Known port mappings for local test microservices
SERVICE_PORT_MAP = {
    "checkout-api": 8080,
    "customer-web": 8081,
    "payments-api": 8082,
}


def _verify_demo_mode_active():
    """Validates that demo mode is actively permitted."""
    current_settings = get_settings()
    if not current_settings.DEMO_MODE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo controls and fault injection are disabled in this environment.",
        )
    if current_settings.APP_ENV == "production" and not current_settings.DEMO_MODE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo controls are strictly prohibited in production.",
        )


async def _dispatch_microservice_chaos(service_name: str, endpoint: str, body: dict) -> bool:
    """
    Attempts to contact the sample microservice chaos endpoint.
    Tries container network host first, then localhost fallback with short timeout.
    Returns True if an HTTP endpoint responded, False otherwise.
    """
    port = SERVICE_PORT_MAP.get(service_name)
    if not port:
        return False

    candidate_urls = [
        f"http://{service_name}:{port}{endpoint}",
        f"http://127.0.0.1:{port}{endpoint}",
        f"http://localhost:{port}{endpoint}",
    ]

    async with httpx.AsyncClient(timeout=0.35) as client:
        for url in candidate_urls:
            try:
                res = await client.post(url, json=body)
                if res.status_code in (200, 201, 204):
                    logger.info("Chaos endpoint '%s' succeeded on '%s'", endpoint, url)
                    return True
            except Exception:
                continue

    return False


@router.get(
    "/status",
    response_model=DemoStatusResponse,
    summary="Get demo mode configuration and service health statuses",
)
async def get_demo_status(
    org: OrgDep,
    current_user: RequireOperatorDep,
    db: DatabaseDep,
) -> DemoStatusResponse:
    """Returns demo mode operational state and monitored service health."""
    _verify_demo_mode_active()

    services_stmt = select(Service).where(Service.organization_id == org.id)
    services_res = await db.execute(services_stmt)
    services = services_res.scalars().all()

    service_statuses: List[DemoServiceStatus] = []
    async with httpx.AsyncClient(timeout=0.8) as client:
        for svc in services:
            reachable = False
            port = SERVICE_PORT_MAP.get(svc.name)
            if port:
                for base in [f"http://{svc.name}:{port}", f"http://127.0.0.1:{port}"]:
                    try:
                        probe_res = await client.get(f"{base}/healthz")
                        if probe_res.status_code in (200, 503, 429):
                            reachable = True
                            break
                    except Exception:
                        continue

            service_statuses.append(DemoServiceStatus(
                service_name=svc.name,
                status=svc.status,
                availability=svc.availability,
                error_rate=svc.error_rate,
                latency_ms=svc.latency_ms,
                chaos_endpoint_reachable=reachable,
            ))

    return DemoStatusResponse(
        demo_mode_enabled=settings.DEMO_MODE_ENABLED,
        recovery_simulation_mode=settings.RECOVERY_SIMULATION_MODE,
        environment=settings.APP_ENV,
        services=service_statuses,
    )


@router.post(
    "/fault",
    response_model=DemoFaultResponse,
    summary="Inject a controlled failure scenario into a monitored microservice",
)
async def inject_demo_fault(
    payload: DemoFaultRequest,
    org: OrgDep,
    current_user: RequireOperatorDep,
    db: DatabaseDep,
) -> DemoFaultResponse:
    """
    Triggers controlled failure simulation on a test microservice.
    Applies configurable error rate, latency, or hard downtime.
    Guarded by RBAC (operator/admin) and DEMO_MODE_ENABLED.
    """
    _verify_demo_mode_active()
    now = datetime.now(timezone.utc)

    # 1. Look up Service in DB
    svc_stmt = select(Service).where(
        Service.name == payload.service_name,
        Service.organization_id == org.id,
    )
    svc_res = await db.execute(svc_stmt)
    service = svc_res.scalars().first()

    if not service:
        # Fallback by name only within org or default
        fallback_stmt = select(Service).where(Service.name == payload.service_name)
        fallback_res = await db.execute(fallback_stmt)
        service = fallback_res.scalars().first()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Monitored service '{payload.service_name}' not found.",
        )

    # 2. Determine chaos parameters based on fault scenario
    endpoint = "/chaos/degrade"
    chaos_body = {}

    if payload.fault_type == "service_down":
        endpoint = "/chaos/fail"
        service.status = "critical"
        service.availability = 0.0
        service.error_rate = 1.0
        service.latency_ms = payload.latency_ms or 5000
    elif payload.fault_type == "http_500":
        service.status = "critical"
        service.error_rate = payload.error_rate or 0.18
        service.latency_ms = payload.latency_ms or 320
        service.availability = 82.0
        chaos_body = {
            "status": "degraded",
            "error_rate": service.error_rate,
            "latency_ms": service.latency_ms,
        }
    elif payload.fault_type == "high_latency":
        service.status = "degraded"
        service.latency_ms = payload.latency_ms or 950
        service.error_rate = payload.error_rate or 0.05
        service.availability = 95.0
        chaos_body = {
            "status": "degraded",
            "latency_ms": service.latency_ms,
            "error_rate": service.error_rate,
        }
    elif payload.fault_type == "cpu_saturation":
        service.status = "degraded"
        service.latency_ms = payload.latency_ms or 750
        service.error_rate = payload.error_rate or 0.08
        service.availability = 92.0
        chaos_body = {
            "status": "degraded",
            "cpu_usage": payload.cpu_usage or 0.95,
            "latency_ms": service.latency_ms,
            "error_rate": service.error_rate,
        }
    else:  # degraded / memory_leak
        service.status = "degraded"
        service.latency_ms = payload.latency_ms or 650
        service.error_rate = payload.error_rate or 0.08
        service.availability = 92.0
        chaos_body = {
            "status": "degraded",
            "memory_bytes": 2147483648,
            "latency_ms": service.latency_ms,
            "error_rate": service.error_rate,
        }

    service.last_checked = now
    service_id_val = service.id

    # 3. Dispatch chaos to microservice if live container exists
    chaos_contacted = await _dispatch_microservice_chaos(service.name, endpoint, chaos_body)

    # 4. Audit Log
    db.add(AuditLog(
        organization_id=org.id,
        user_id=current_user.id,
        action="demo_fault_triggered",
        resource_type="service",
        resource_id=service_id_val,
        details=(
            f"Operator '{current_user.email}' triggered controlled fault '{payload.fault_type}' "
            f"on service '{service.name}' (error_rate={service.error_rate}, latency={service.latency_ms}ms, "
            f"chaos_contacted={chaos_contacted})."
        ),
    ))

    await db.commit()

    # 5. Broadcast real-time SSE event
    await event_broadcaster.broadcast(org.id, "service_health", {
        "id": service_id_val,
        "name": service.name,
        "status": service.status,
        "availability": service.availability,
        "errorRate": service.error_rate,
        "latencyMs": service.latency_ms,
    })

    return DemoFaultResponse(
        status="success",
        service_name=service.name,
        fault_type=payload.fault_type,
        message=(
            f"Controlled fault '{payload.fault_type}' successfully applied to '{service.name}'. "
            f"Telemetry degraded (error_rate={service.error_rate * 100:.1f}%, latency={service.latency_ms}ms)."
        ),
        metrics={
            "status": service.status,
            "availability": service.availability,
            "error_rate": service.error_rate,
            "latency_ms": service.latency_ms,
            "live_container_updated": chaos_contacted,
        },
        timestamp=now.isoformat(),
    )


@router.post(
    "/reset",
    response_model=DemoResetResponse,
    summary="Restore monitored services in the demo environment to normal health",
)
async def reset_demo_environment(
    payload: DemoResetRequest,
    org: OrgDep,
    current_user: RequireOperatorDep,
    db: DatabaseDep,
) -> DemoResetResponse:
    """
    Restores one or all monitored test services to clean healthy state.
    Sends /chaos/recover to sample microservices and normalizes database records.
    """
    _verify_demo_mode_active()
    now = datetime.now(timezone.utc)

    stmt = select(Service).where(Service.organization_id == org.id)
    if payload.service_name:
        stmt = stmt.where(Service.name == payload.service_name)

    res = await db.execute(stmt)
    services = res.scalars().all()

    if not services and payload.service_name:
        # Fallback search by name
        fb_stmt = select(Service).where(Service.name == payload.service_name)
        fb_res = await db.execute(fb_stmt)
        services = fb_res.scalars().all()

    restored_names: List[str] = []

    for svc in services:
        # 1. Reset microservice chaos state
        await _dispatch_microservice_chaos(svc.name, "/chaos/recover", {})

        # 2. Reset database service telemetry
        svc.status = "healthy"
        svc.availability = 99.98
        svc.error_rate = 0.01
        svc.latency_ms = 22
        svc.last_checked = now
        restored_names.append(svc.name)

        # 3. Broadcast real-time SSE health
        await event_broadcaster.broadcast(org.id, "service_health", {
            "id": svc.id,
            "name": svc.name,
            "status": svc.status,
            "availability": svc.availability,
            "errorRate": svc.error_rate,
            "latencyMs": svc.latency_ms,
        })

    # 4. Audit Log
    db.add(AuditLog(
        organization_id=org.id,
        user_id=current_user.id,
        action="demo_reset",
        resource_type="organization",
        resource_id=str(org.id),
        details=f"Operator '{current_user.email}' reset demo environment. Restored services: {', '.join(restored_names)}.",
    ))

    await db.commit()

    return DemoResetResponse(
        status="success",
        restored_services=restored_names,
        message=f"Restored {len(restored_names)} service(s) to healthy baseline.",
        timestamp=now.isoformat(),
    )


@router.post(
    "/simulate-alert",
    response_model=DemoSimulateAlertResponse,
    summary="Directly inject a verified Alertmanager alert into the incident detection pipeline",
)
async def simulate_demo_alert(
    payload: DemoSimulateAlertRequest,
    org: OrgDep,
    current_user: RequireOperatorDep,
    db: DatabaseDep,
) -> DemoSimulateAlertResponse:
    """
    Dispatches a structured alert into the incident creation pipeline.
    Validates alert handling, deduplication, AI root cause diagnosis, and recovery recommendation.
    Optionally enqueues a pending recovery action ready for operator approval.
    """
    _verify_demo_mode_active()
    now = datetime.now(timezone.utc)

    # 1. Look up Service
    svc_stmt = select(Service).where(
        Service.name == payload.service_name,
        Service.organization_id == org.id,
    )
    svc_res = await db.execute(svc_stmt)
    service = svc_res.scalars().first()

    if not service:
        # Fallback by name
        fb_stmt = select(Service).where(Service.name == payload.service_name)
        fb_res = await db.execute(fb_stmt)
        service = fb_res.scalars().first()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{payload.service_name}' was not found.",
        )

    # 2. Check for existing active incident to test deduplication
    active_inc_stmt = (
        select(Incident)
        .where(
            Incident.service_id == service.id,
            Incident.status.in_(["open", "investigating", "recovering"]),
        )
        .order_by(Incident.created_at.desc())
    )
    active_inc_res = await db.execute(active_inc_stmt)
    existing_incident = active_inc_res.scalars().first()

    summary_text = payload.summary or f"Critical alert '{payload.alertname}' firing on {payload.service_name}"
    desc_text = payload.description or f"Telemetry threshold breached. Error rate is elevated on {payload.service_name}."

    if existing_incident:
        # Deduplication flow
        existing_incident.updated_at = now
        existing_incident.severity = payload.severity

        db.add(IncidentEvent(
            incident_id=existing_incident.id,
            label="Alert Re-triggered",
            detail=desc_text,
            timestamp=now,
            tone="warning",
        ))

        db.add(AuditLog(
            organization_id=org.id,
            user_id=current_user.id,
            action="incident_deduplicated",
            resource_type="incident",
            resource_id=existing_incident.id,
            details=f"Deduplicated demo alert '{payload.alertname}' for active incident '{existing_incident.id}'.",
        ))

        await db.commit()

        await event_broadcaster.broadcast(org.id, "incident_updated", {
            "id": existing_incident.id,
            "status": existing_incident.status,
            "severity": existing_incident.severity,
        })

        return DemoSimulateAlertResponse(
            status="deduplicated",
            incident_id=existing_incident.id,
            recovery_id=None,
            recommended_action=existing_incident.recommended_action,
            message=f"Deduplicated alert '{payload.alertname}' onto existing active incident '{existing_incident.id}'.",
        )

    # 3. Create New Incident
    all_inc_stmt = select(Incident)
    all_inc_res = await db.execute(all_inc_stmt)
    count = len(all_inc_res.scalars().all()) + 1001
    incident_id = f"INC-{count}"

    recommended_action = normalize_action(payload.recommended_action or "restart_service")

    new_incident = Incident(
        id=incident_id,
        organization_id=service.organization_id,
        service_id=service.id,
        service_name=service.name,
        title=summary_text,
        severity=payload.severity,
        status="open",
        detected_at=now,
        recovery_status="Approval required",
        error_rate=service.error_rate if service.error_rate > 0 else 0.15,
        threshold=0.01,
        probable_cause=payload.probable_cause or "Telemetry breach detected by monitoring rule",
        recommended_action=recommended_action,
    )
    db.add(new_incident)
    await db.flush()

    # Add evidence
    db.add(IncidentEvidence(
        incident_id=new_incident.id,
        kind="metric",
        title=payload.alertname,
        detail=desc_text,
        timestamp=now,
    ))

    # Add initial event
    db.add(IncidentEvent(
        incident_id=new_incident.id,
        label="Incident Detected",
        detail=desc_text,
        timestamp=now,
        tone="warning",
    ))

    # 4. Trigger AI Diagnosis
    ai_provider = get_ai_provider()
    try:
        diag = await ai_provider.diagnose({
            "service_name": service.name,
            "alert_name": payload.alertname,
            "severity": payload.severity,
            "error_rate": new_incident.error_rate,
            "latency_ms": service.latency_ms,
            "description": desc_text,
            "probable_cause": payload.probable_cause,
        })
        new_incident.probable_cause = diag.probable_root_cause
        if is_action_allowed(diag.recommended_action):
            new_incident.recommended_action = diag.recommended_action

        db.add(IncidentEvidence(
            incident_id=new_incident.id,
            kind="log",
            title="AI Root Cause Analysis",
            detail=f"{diag.probable_root_cause} (Risk: {diag.risk_level})",
            timestamp=now,
        ))
        db.add(IncidentEvent(
            incident_id=new_incident.id,
            label="AI Diagnosis Generated",
            detail=f"Recommended: {new_incident.recommended_action} (Confidence: {int(diag.confidence_score * 100)}%)",
            timestamp=now,
            tone="neutral",
        ))
    except Exception as e:
        logger.warning("AI diagnosis error in demo simulation: %s", e)

    # 5. Optionally enqueue RecoveryAction in pending_approval state
    recovery_id = None
    if payload.auto_request_recovery:
        rec_count_res = await db.execute(select(RecoveryAction))
        rec_count = len(rec_count_res.scalars().all()) + 800
        recovery_id = f"REC-{rec_count}"

        rec_action = RecoveryAction(
            id=recovery_id,
            incident_id=new_incident.id,
            service_id=service.id,
            service_name=service.name,
            action=new_incident.recommended_action,
            status="pending_approval",
            approval_required=True,
            requested_by=current_user.email,
            requested_at=now,
            verification="pending",
        )
        db.add(rec_action)
        new_incident.status = "recovering"
        new_incident.recovery_status = "Approval required"

        db.add(IncidentEvent(
            incident_id=new_incident.id,
            label="Recovery Enqueued",
            detail=f"Recommended action '{new_incident.recommended_action}' awaiting operator approval.",
            timestamp=now,
            tone="neutral",
        ))

    # Audit log
    db.add(AuditLog(
        organization_id=org.id,
        user_id=current_user.id,
        action="demo_alert_simulated",
        resource_type="incident",
        resource_id=new_incident.id,
        details=f"Simulated alert '{payload.alertname}' on '{service.name}'. Incident '{new_incident.id}' created.",
    ))

    await db.commit()

    # Broadcast SSE events
    await event_broadcaster.broadcast(org.id, "incident_created", {
        "id": new_incident.id,
        "title": new_incident.title,
        "serviceName": new_incident.service_name,
        "severity": new_incident.severity,
        "status": new_incident.status,
    })

    if recovery_id:
        await event_broadcaster.broadcast(org.id, "recovery_updated", {
            "id": recovery_id,
            "incidentId": new_incident.id,
            "serviceName": service.name,
            "action": new_incident.recommended_action,
            "status": "pending_approval",
            "approvalRequired": True,
        })

    return DemoSimulateAlertResponse(
        status="created",
        incident_id=new_incident.id,
        recovery_id=recovery_id,
        recommended_action=new_incident.recommended_action,
        message=f"Incident '{new_incident.id}' created with evidence and AI diagnosis.",
    )
