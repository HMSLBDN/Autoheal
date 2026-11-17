"""
AutoHeal DevOps — Health, Liveness & Readiness Probes
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, Response, status
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])
settings = get_settings()


@router.get(
    "/health",
    summary="Service health probe",
    status_code=status.HTTP_200_OK,
)
async def get_health() -> Dict[str, str]:
    """
    Public health probe consumed by frontend healthApi.get().
    Contract requires: { "status": str, "timestamp": str }
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": settings.APP_ENV,
        "version": settings.APP_VERSION,
    }


@router.get(
    "/health/liveness",
    summary="Container liveness probe",
    status_code=status.HTTP_200_OK,
)
async def get_liveness() -> Dict[str, str]:
    """
    Minimal liveness check for Kubernetes / Docker container health checks.
    Confirms the ASGI event loop is active and responsive.
    """
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/health/readiness",
    summary="Deep readiness probe checking database and redis dependencies",
)
async def get_readiness(
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Deep readiness probe checking database connectivity and Redis broker availability.
    Returns HTTP 200 when ready to receive traffic, or HTTP 503 if any dependency is degraded.
    """
    checks = {
        "database": "unknown",
        "redis": "unknown",
    }
    is_ready = True

    # 1. Test database connection
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as db_err:
        logger.warning("Readiness probe database check failed: %s", db_err)
        checks["database"] = f"unhealthy: {type(db_err).__name__}"
        is_ready = False

    # 2. Test Redis connection
    try:
        client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2.0)
        await client.ping()
        await client.aclose()
        checks["redis"] = "healthy"
    except Exception as redis_err:
        logger.warning("Readiness probe Redis check failed: %s", redis_err)
        checks["redis"] = f"unhealthy: {type(redis_err).__name__}"
        is_ready = False

    status_str = "ready" if is_ready else "degraded"
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": status_str,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": checks,
    }
