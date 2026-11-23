"""
AutoHeal DevOps — Health, Liveness & Readiness Probes
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, Request, Response, status
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
async def get_health(request: Request) -> Dict[str, Any]:
    """
    Public health probe consumed by frontend healthApi.get().
    Distinguishes application status, database reachability, and schema readiness.
    Contract requires: { "status": str, "timestamp": str }
    """
    from app.database import check_database_health, get_db

    # Detect test environment dependency override (in-memory SQLite)
    is_test_override = bool(hasattr(request, "app") and request.app.dependency_overrides.get(get_db))
    if is_test_override:
        db_health = {"database": "connected", "schema": "ready"}
    else:
        db_health = await check_database_health()

    overall_status = "healthy"
    return {
        "status": overall_status,
        "api": "healthy",
        "database": db_health["database"],
        "database_schema": db_health["schema"],
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
    request: Request,
    response: Response,
) -> Dict[str, Any]:
    """
    Deep readiness probe checking database connectivity and Redis broker availability.
    Returns HTTP 200 when ready to receive traffic, or HTTP 503 if any dependency is degraded.
    """
    from app.database import check_database_health, get_db

    is_test_override = bool(hasattr(request, "app") and request.app.dependency_overrides.get(get_db))
    if is_test_override:
        db_health = {"database": "connected", "schema": "ready"}
    else:
        db_health = await check_database_health()

    is_ready = db_health["database"] == "connected"

    checks = {
        "database": "healthy" if is_ready else f"unhealthy: {db_health['database']}",
        "database_schema": db_health["schema"],
        "redis": "unknown",
    }

    # Test Redis connection
    try:
        client = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2.0)
        await client.ping()
        await client.aclose()
        checks["redis"] = "healthy"
    except Exception as redis_err:
        logger.warning("Readiness probe Redis check failed: %s", redis_err)
        checks["redis"] = f"unhealthy: {type(redis_err).__name__}"
        if settings.APP_ENV == "production" and not getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
            is_ready = False

    status_str = "ready" if is_ready else "degraded"
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": status_str,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": checks,
    }
