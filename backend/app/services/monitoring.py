"""
AutoHeal DevOps — Background Monitoring & Metrics Collector Service
Integrates Prometheus metric queries, probes HTTP health endpoints,
updates Service health state, and records time-series metrics.
"""

from datetime import datetime, timezone
import logging
import time
from typing import Dict, List, Optional
import httpx
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.audit import AuditLog
from app.models.incident import Incident, IncidentEvent, IncidentEvidence
from app.models.metric import ServiceMetric
from app.models.recovery import RecoveryAction
from app.models.service import Service, ServiceMonitor
from app.services.ai.factory import get_ai_provider
from app.services.events import event_broadcaster
from app.services.recovery.registry import is_action_allowed, normalize_action

logger = logging.getLogger(__name__)
settings = get_settings()

SERVICE_PORT_MAP = {
    "checkout-api": 8080,
    "customer-web": 8081,
    "payments-api": 8082,
}


class ServiceHealthSnapshot(BaseModel):
    """Snapshot of a service's evaluated health and performance."""
    service_id: str
    status: str  # healthy, degraded, critical
    availability: float
    error_rate: float
    latency_ms: int
    cpu_percent: float
    memory_percent: float
    request_rate: float
    sampled_at: datetime
    is_reachable: bool
    diagnostic_message: Optional[str] = None


class MonitoringService:
    """
    Coordinates infrastructure monitoring cycles across registered services.
    Supports Prometheus API scraping with graceful degradation on unreachable endpoints.
    """

    _prom_reachable: Optional[bool] = None
    _prom_checked_at: float = 0.0

    def __init__(self, prometheus_url: Optional[str] = None):
        self.prometheus_url = prometheus_url or settings.PROMETHEUS_URL

    async def is_prometheus_available(self, client: httpx.AsyncClient) -> bool:
        """Checks if Prometheus instance is reachable, caching result for 30s."""
        now = time.time()
        if MonitoringService._prom_reachable is not None and (now - MonitoringService._prom_checked_at) < 30.0:
            return MonitoringService._prom_reachable

        MonitoringService._prom_checked_at = now
        try:
            res = await client.get(f"{self.prometheus_url.rstrip('/')}/-/healthy", timeout=0.3)
            MonitoringService._prom_reachable = (res.status_code == 200)
        except Exception:
            MonitoringService._prom_reachable = False
        return MonitoringService._prom_reachable

    async def query_prometheus_metric(
        self, client: httpx.AsyncClient, query: str
    ) -> Optional[float]:
        """Queries Prometheus Instant Query API (/api/v1/query) for a single scalar value."""
        if not await self.is_prometheus_available(client):
            return None
        try:
            url = f"{self.prometheus_url.rstrip('/')}/api/v1/query"
            res = await client.get(url, params={"query": query}, timeout=1.0)
            if res.status_code == 200:
                data = res.json()
                results = data.get("data", {}).get("result", [])
                if results and "value" in results[0]:
                    val = float(results[0]["value"][1])
                    return val
        except Exception as e:
            logger.debug("Prometheus query '%s' failed or server unreachable: %s", query, e)
        return None

    async def probe_service(
        self,
        service: Service,
        monitor: Optional[ServiceMonitor] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> ServiceHealthSnapshot:
        """
        Evaluates health and performance metrics for a specific service.
        Tests health endpoint and aggregates telemetry metrics.
        """
        now = datetime.now(timezone.utc)
        timeout = monitor.timeout_seconds if monitor else 2.5
        health_path = monitor.health_check_path if monitor else "/health"

        # Determine target port for service
        port = SERVICE_PORT_MAP.get(service.name)
        if not port:
            if "checkout" in service.name:
                port = 8080
            elif "web" in service.name:
                port = 8081
            elif "payment" in service.name:
                port = 8082
            else:
                port = 8080

        import os
        in_docker = os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER") == "true" or os.environ.get("CONTAINER") == "true"
        if in_docker:
            candidate_bases = [
                f"http://{service.name}:{port}",
                f"http://127.0.0.1:{port}",
            ]
        else:
            candidate_bases = [
                f"http://127.0.0.1:{port}",
            ]

        own_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=timeout)
            own_client = True

        is_reachable = False
        status = "healthy"
        availability = service.availability or 99.9
        error_rate = service.error_rate or 0.05
        latency_ms = service.latency_ms or 120
        cpu_percent = 25.0
        memory_percent = 35.0
        request_rate = 140.0
        diag_msg = None

        try:
            # 1. Probe health check endpoint across candidate endpoints
            for base in candidate_bases:
                try:
                    probe_url = f"{base}{health_path}"
                    probe_start = time.time()
                    probe_res = await client.get(probe_url, timeout=min(timeout, 0.3))
                    probe_lat = int((time.time() - probe_start) * 1000)

                    # Also query status for live metrics if available
                    status_data = {}
                    try:
                        st_res = await client.get(f"{base}/status", timeout=0.8)
                        if st_res.status_code == 200:
                            status_data = st_res.json()
                    except Exception:
                        pass

                    # Parse body payload to inspect if microservice self-reports unhealthy state
                    probe_body = {}
                    try:
                        probe_body = probe_res.json()
                    except Exception:
                        pass

                    is_body_unhealthy = (
                        probe_body.get("status") in ("unhealthy", "critical", "degraded")
                        or status_data.get("status") in ("unhealthy", "critical", "degraded")
                        or float(probe_body.get("error_rate", 0.0)) >= 0.5
                    )

                    is_reachable = True
                    if probe_res.status_code == 200 and not is_body_unhealthy:
                        status = "healthy"
                        availability = 99.98
                        raw_err = float(status_data.get("error_rate", probe_body.get("error_rate", 0.0)))
                        error_rate = raw_err * 100.0 if 0.0 < raw_err <= 1.0 else raw_err
                        latency_ms = int(status_data.get("latency_ms", probe_lat))
                        cpu_percent = round(float(status_data.get("cpu_usage", 0.20)) * 100, 1)
                        memory_bytes = float(status_data.get("memory_bytes", 268435456))
                        memory_percent = round((memory_bytes / (1024**3)) * 100, 1)
                        diag_msg = f"Live health probe HTTP 200 OK ({latency_ms}ms)"
                    elif probe_res.status_code in (429, 500, 502, 503, 504) or is_body_unhealthy:
                        is_crit = probe_res.status_code in (500, 502, 503) or is_body_unhealthy
                        status = "critical" if is_crit else "degraded"
                        availability = 0.0 if status == "critical" else 88.0
                        raw_err = float(status_data.get("error_rate", probe_body.get("error_rate", 1.0)))
                        error_rate = 100.0 if status == "critical" else (raw_err * 100.0 if 0.0 < raw_err <= 1.0 else max(raw_err, 8.5))
                        latency_ms = int(status_data.get("latency_ms", probe_lat))
                        status_str = f"HTTP {probe_res.status_code}" if probe_res.status_code != 200 else "unhealthy payload"
                        diag_msg = f"Live health probe detected failure ({status_str})"
                    else:
                        status = "critical"
                        availability = 0.0
                        error_rate = 100.0
                        diag_msg = f"Live health probe failed with HTTP {probe_res.status_code}"
                    break
                except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as net_err:
                    logger.debug("Candidate '%s' not reachable: %s", base, net_err)
                    continue

            # 2. Query Prometheus metrics if Prometheus is reachable
            prom_err = await self.query_prometheus_metric(
                client, f'rate(http_requests_total{{service="{service.name}",status=~"5.." }}[2m])'
            )
            if prom_err is not None:
                error_rate = round(prom_err * 100, 2)

            prom_lat = await self.query_prometheus_metric(
                client, f'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{{service="{service.name}"}}[2m]))'
            )
            if prom_lat is not None:
                latency_ms = int(prom_lat * 1000)

            prom_cpu = await self.query_prometheus_metric(
                client, f'process_cpu_usage{{service="{service.name}"}}'
            )
            if prom_cpu is not None:
                cpu_percent = round(prom_cpu * 100, 1)

            # If not reachable via live microservice, maintain existing service state in test environments
            if not is_reachable:
                if service.status in ("critical", "degraded"):
                    status = service.status
                    availability = service.availability or 0.0
                    error_rate = service.error_rate or 15.0
                    latency_ms = service.latency_ms or 500
                    diag_msg = f"Service '{service.name}' endpoint unreachable"
                else:
                    status = "healthy"
                    diag_msg = "No live microservice detected (simulated baseline maintained)"
            else:
                # Determine overall service status from evaluated telemetry
                if error_rate > 5.0 or availability < 90.0:
                    status = "critical"
                elif error_rate > 1.0 or latency_ms > 400:
                    status = "degraded"
                else:
                    status = "healthy"

        finally:
            if own_client:
                await client.aclose()

        return ServiceHealthSnapshot(
            service_id=service.id,
            status=status,
            availability=availability,
            error_rate=error_rate,
            latency_ms=latency_ms,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            request_rate=request_rate,
            sampled_at=now,
            is_reachable=is_reachable,
            diagnostic_message=diag_msg,
        )

    async def run_monitoring_cycle(self, db: AsyncSession) -> List[ServiceMetric]:
        """
        Executes a complete monitoring collection pass across all active services.
        Persists time-series metrics, updates service states, detects real failures,
        and creates genuine incidents with AI diagnosis and enqueued recovery.
        """
        stmt = select(Service).options(selectinload(Service.monitors))
        result = await db.execute(stmt)
        services = result.scalars().all()

        recorded_metrics: List[ServiceMetric] = []
        now = datetime.now(timezone.utc)
        ai_provider = get_ai_provider()

        async with httpx.AsyncClient(timeout=4.0) as client:
            for svc in services:
                monitor = svc.monitors[0] if svc.monitors else None
                snapshot = await self.probe_service(svc, monitor=monitor, client=client)

                # 1. Update Service table
                svc.status = snapshot.status
                svc.availability = snapshot.availability
                svc.error_rate = snapshot.error_rate
                svc.latency_ms = snapshot.latency_ms
                svc.last_checked = snapshot.sampled_at

                # 2. Record new Metric point
                metric_entry = ServiceMetric(
                    service_id=svc.id,
                    sampled_at=snapshot.sampled_at,
                    cpu_percent=snapshot.cpu_percent,
                    memory_percent=snapshot.memory_percent,
                    request_rate=snapshot.request_rate,
                    error_rate=snapshot.error_rate,
                    latency_ms=snapshot.latency_ms,
                    availability=snapshot.availability,
                )
                db.add(metric_entry)
                recorded_metrics.append(metric_entry)

                await event_broadcaster.broadcast(svc.organization_id, "service_health", {
                    "id": svc.id,
                    "name": svc.name,
                    "status": svc.status,
                    "availability": svc.availability,
                    "errorRate": svc.error_rate,
                    "latencyMs": svc.latency_ms,
                    "lastChecked": snapshot.sampled_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
                })

                # 3. Automated Failure Detection & Real-Time Incident Creation
                if snapshot.status in ("critical", "degraded") and snapshot.is_reachable:
                    # Check for existing active incident to prevent duplicate creation
                    active_inc_stmt = (
                        select(Incident)
                        .where(
                            Incident.service_id == svc.id,
                            Incident.status.in_(["open", "investigating", "recovering", "escalated"]),
                        )
                        .order_by(desc(Incident.created_at))
                    )
                    active_res = await db.execute(active_inc_stmt)
                    existing_incident = active_res.scalars().first()

                    if existing_incident:
                        # Intra-monitoring deduplication: update timestamp and error rate
                        existing_incident.updated_at = snapshot.sampled_at
                        existing_incident.error_rate = round(snapshot.error_rate, 2)
                        await event_broadcaster.broadcast(svc.organization_id, "incident_updated", {
                            "id": existing_incident.id,
                            "status": existing_incident.status,
                            "errorRate": existing_incident.error_rate,
                        })
                    else:
                        # Generate collision-free incident ID
                        all_inc_res = await db.execute(select(Incident.id))
                        existing_ids = set(all_inc_res.scalars().all())
                        count = len(existing_ids) + 1001
                        incident_id = f"INC-{count}"
                        while incident_id in existing_ids:
                            count += 1
                            incident_id = f"INC-{count}"

                        severity = "critical" if snapshot.status == "critical" or snapshot.error_rate >= 15.0 else "high"

                        # Evidence-based root-cause diagnosis
                        if snapshot.status == "critical":
                            probable_cause = f"Health probe failure ({snapshot.diagnostic_message or 'HTTP 503'}). Upstream container or service is degraded."
                            recommended_action = "restart_service"
                            confidence = 0.90
                        elif snapshot.error_rate > 1.0:
                            probable_cause = f"Elevated 5xx error rate ({snapshot.error_rate:.1f}%) breaching configured SLA threshold (1.0%)."
                            recommended_action = "rollback_deployment"
                            confidence = 0.85
                        else:
                            probable_cause = f"High latency ({snapshot.latency_ms}ms) exceeding performance budget."
                            recommended_action = "scale_replicas"
                            confidence = 0.80

                        # Enrich with AI Provider diagnosis if available
                        try:
                            diag = await ai_provider.diagnose({
                                "service_name": svc.name,
                                "alert_name": "HealthProbeFailure",
                                "severity": severity,
                                "error_rate": snapshot.error_rate,
                                "latency_ms": snapshot.latency_ms,
                                "description": snapshot.diagnostic_message or "Health probe failure",
                                "probable_cause": probable_cause,
                            })
                            if diag and diag.probable_root_cause:
                                probable_cause = diag.probable_root_cause
                            if diag and is_action_allowed(diag.recommended_action):
                                recommended_action = normalize_action(diag.recommended_action)
                        except Exception as ai_err:
                            logger.debug("AI diagnosis fallback used: %s", ai_err)

                        new_incident = Incident(
                            id=incident_id,
                            organization_id=svc.organization_id,
                            service_id=svc.id,
                            service_name=svc.name,
                            title=f"Health probe failure on {svc.name}",
                            severity=severity,
                            status="open",
                            detected_at=snapshot.sampled_at,
                            recovery_status="Approval required",
                            error_rate=round(snapshot.error_rate, 2),
                            threshold=1.0,
                            probable_cause=probable_cause,
                            recommended_action=recommended_action,
                        )
                        db.add(new_incident)
                        await db.flush()

                        # Attach supporting evidence
                        db.add(IncidentEvidence(
                            incident_id=new_incident.id,
                            kind="health_check",
                            title="Health Probe Result",
                            detail=snapshot.diagnostic_message or "Live health check returned non-200 status",
                            timestamp=snapshot.sampled_at,
                        ))
                        db.add(IncidentEvidence(
                            incident_id=new_incident.id,
                            kind="metric",
                            title="Telemetry Snapshot",
                            detail=f"Availability {snapshot.availability}%, Error rate {snapshot.error_rate:.1f}%, Latency {snapshot.latency_ms}ms",
                            timestamp=snapshot.sampled_at,
                        ))

                        # Add event timeline
                        db.add(IncidentEvent(
                            incident_id=new_incident.id,
                            label="Incident Detected",
                            detail=f"Monitoring detected {snapshot.status.upper()} state on {svc.name}: {snapshot.diagnostic_message}",
                            timestamp=snapshot.sampled_at,
                            tone="warning",
                        ))
                        db.add(IncidentEvent(
                            incident_id=new_incident.id,
                            label="Diagnosis Completed",
                            detail=f"Probable cause: {probable_cause}. Recommended: {recommended_action} (Confidence: {int(confidence * 100)}%)",
                            timestamp=snapshot.sampled_at,
                            tone="neutral",
                        ))

                        # Enqueue policy-gated recovery action requiring operator approval
                        rec_res = await db.execute(select(RecoveryAction.id))
                        rec_ids = set(rec_res.scalars().all())
                        rec_num = len(rec_ids) + 800
                        recovery_id = f"REC-{rec_num}"
                        while recovery_id in rec_ids:
                            rec_num += 1
                            recovery_id = f"REC-{rec_num}"

                        rec_action = RecoveryAction(
                            id=recovery_id,
                            incident_id=new_incident.id,
                            service_id=svc.id,
                            service_name=svc.name,
                            action=recommended_action,
                            status="pending_approval",
                            approval_required=True,
                            requested_by="AutoHeal Monitor",
                            requested_at=snapshot.sampled_at,
                            verification="pending",
                            execution_mode="SIMULATED",
                            evidence_classification="SIMULATED",
                        )
                        db.add(rec_action)
                        new_incident.status = "recovering"
                        new_incident.recovery_status = "Approval required"

                        db.add(IncidentEvent(
                            incident_id=new_incident.id,
                            label="Recovery Enqueued",
                            detail=f"Recommended action '{recommended_action}' enqueued; awaiting operator approval.",
                            timestamp=snapshot.sampled_at,
                            tone="neutral",
                        ))

                        db.add(AuditLog(
                            organization_id=svc.organization_id,
                            action="incident_detected_by_monitoring",
                            resource_type="incident",
                            resource_id=new_incident.id,
                            details=f"Monitoring detected failure on '{svc.name}'. Created incident '{new_incident.id}' and enqueued recovery '{recovery_id}'.",
                        ))

                        await db.commit()

                        # Broadcast SSE events for instant UI synchronization
                        await event_broadcaster.broadcast(svc.organization_id, "incident_created", {
                            "id": new_incident.id,
                            "title": new_incident.title,
                            "serviceName": new_incident.service_name,
                            "severity": new_incident.severity,
                            "status": new_incident.status,
                        })
                        await event_broadcaster.broadcast(svc.organization_id, "recovery_updated", {
                            "id": recovery_id,
                            "incidentId": new_incident.id,
                            "serviceName": svc.name,
                            "action": recommended_action,
                            "status": "pending_approval",
                            "approvalRequired": True,
                        })

        await db.commit()
        return recorded_metrics
