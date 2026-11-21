"""
AutoHeal DevOps — Observability & Tracing API Router
Exposes Prometheus metric exposition, high-level SLA/SLO statistics,
and OpenTelemetry distributed traces for the Observability Center.
"""

from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DatabaseDep, get_current_user, get_current_org
from app.core.metrics import enterprise_metrics
from app.core.telemetry import trace_buffer
from app.database import async_engine
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/observability", tags=["Observability & Telemetry"])


def _get_engine_pool_stats() -> Dict[str, int]:
    """Retrieves current connection pool utilization metrics."""
    pool = getattr(async_engine, "sync_engine", None)
    if pool and hasattr(pool, "pool"):
        p = pool.pool
        return {
            "pool_size": getattr(p, "size", lambda: 10)(),
            "checked_out": getattr(p, "checkedout", lambda: 0)(),
            "overflow": getattr(p, "overflow", lambda: 0)(),
        }
    return {"pool_size": 10, "checked_out": 0, "overflow": 0}


@router.get("/metrics")
async def get_prometheus_metrics(accept: Optional[str] = Header(None)):
    """
    Exposes Prometheus format metrics for scraping, or JSON if requested.
    """
    pool_stats = _get_engine_pool_stats()

    if accept and "application/json" in accept:
        return enterprise_metrics.get_summary_stats(pool_stats)

    text_content = enterprise_metrics.render_prometheus_text(pool_stats)
    return Response(content=text_content, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/stats")
async def get_observability_stats(
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
):
    """
    Returns real-time telemetry stats for the frontend Observability Center.
    """
    pool_stats = _get_engine_pool_stats()
    stats = enterprise_metrics.get_summary_stats(pool_stats)
    return {
        "status": "success",
        "data": stats,
    }


@router.get("/traces")
async def get_recent_traces(
    limit: int = 50,
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
):
    """
    Retrieves recent distributed OpenTelemetry spans from the circular buffer.
    """
    traces = trace_buffer.get_recent(limit=limit)
    return {
        "status": "success",
        "count": len(traces),
        "traces": traces,
    }
