"""
AutoHeal DevOps — FastAPI Application Entry Point
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings
from app.core.logging import RequestTracingMiddleware, telemetry
from app.database import engine

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifecycle management (startup and graceful shutdown).
    """
    # Startup: Initialize runtime and log configuration
    logger.info("Initializing %s (version: %s, env: %s)...", settings.APP_NAME, settings.APP_VERSION, settings.APP_ENV)

    # Optional background monitoring loop for live development and expo demonstrations
    monitor_task = None
    if settings.APP_ENV == "development" or getattr(settings, "DEMO_MODE_ENABLED", False):
        import asyncio
        from app.database import async_session_factory
        from app.services.monitoring import MonitoringService

        async def _background_monitoring_loop():
            logger.info("AutoHeal real-time background monitoring loop started.")
            while True:
                try:
                    await asyncio.sleep(5)
                    async with async_session_factory() as session:
                        mon_svc = MonitoringService()
                        await mon_svc.run_monitoring_cycle(session)
                except asyncio.CancelledError:
                    break
                except Exception as loop_err:
                    logger.debug("Background monitoring cycle skipped: %s", loop_err)

        monitor_task = asyncio.create_task(_background_monitoring_loop())

    yield

    # Cancel background monitoring loop on shutdown
    if monitor_task:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

    # Shutdown: Cleanly close background executors, Redis connections, DB pools
    logger.info("Gracefully terminating %s runtime...", settings.APP_NAME)
    try:
        from app.database import engine
        await engine.dispose()
        logger.info("Database engine connection pool disposed cleanly.")
    except Exception as exc:
        logger.warning("Error disposing database pool during shutdown: %s", exc)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Autonomous self-healing DevOps operations platform API",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

# Add Request Tracing correlation middleware
app.add_middleware(RequestTracingMiddleware)

# Configure Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"^https://autoheal-omega(-[a-z0-9-]+)?\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Mount API v1 router registry
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Global catch-all exception handler that sanitizes internal stack traces
    while logging detailed errors correlated with the unique request ID.
    Classifies database outages and returns safe user responses.
    """
    request_id = (
        getattr(request.state, "request_id", None)
        or request.headers.get("X-Request-ID")
        or request.headers.get("x-vercel-id")
        or "unknown"
    )

    # Classify error category safely
    exc_module = getattr(exc.__class__, "__module__", "")
    exc_name = exc.__class__.__name__
    is_db_error = any(mod in exc_module for mod in ("sqlalchemy", "asyncpg", "psycopg")) or "connect()" in str(exc)
    category = "database_connection" if is_db_error else "internal_server_error"

    logger.error(
        "request_unhandled_error method=%s path=%s request_id=%s category=%s error_type=%s: %s",
        request.method,
        request.url.path,
        request_id,
        category,
        exc_name,
        str(exc),
        exc_info=True,
    )

    status_code = 503 if is_db_error else 500
    user_detail = (
        f"Database service temporarily unavailable. Please quote request ID {request_id} to support."
        if is_db_error
        else f"An unexpected internal error occurred. Please quote request ID {request_id} to support."
    )

    response_headers = {
        "X-Request-ID": request_id,
        "Cache-Control": "no-store",
    }
    if request.headers.get("x-vercel-id"):
        response_headers["x-vercel-id"] = request.headers["x-vercel-id"]

    return JSONResponse(
        status_code=status_code,
        content={
            "detail": user_detail,
            "request_id": request_id,
            "category": category,
        },
        headers=response_headers,
    )


@app.get(
    "/metrics",
    response_class=PlainTextResponse,
    include_in_schema=False,
    summary="Prometheus exposition metrics endpoint",
)
async def metrics() -> PlainTextResponse:
    """Exposes application runtime telemetry metrics for Prometheus scraping."""
    pool = getattr(engine, "pool", None)
    pool_size = pool.size() if pool and hasattr(pool, "size") else 0
    try:
        pool_overflow = max(0, pool.overflow()) if pool and hasattr(pool, "overflow") else 0
    except Exception:
        pool_overflow = 0
    try:
        pool_checkedout = pool.checkedout() if pool and hasattr(pool, "checkedout") else 0
    except Exception:
        pool_checkedout = 0

    content = telemetry.generate_prometheus_metrics(
        pool_size=pool_size,
        pool_overflow=pool_overflow,
        pool_checkedout=pool_checkedout,
    )
    return PlainTextResponse(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get(
    "/health",
    tags=["Health"],
    summary="Root service health probe",
    status_code=200,
)
async def root_health() -> Dict[str, str]:
    """
    Root-level public health probe for external load balancers, container orchestrators, and CDN probes.
    """
    from datetime import datetime, timezone
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": settings.APP_ENV,
        "version": settings.APP_VERSION,
    }


@app.get(
    "/",
    tags=["Root"],
    summary="Root metadata endpoint",
)
async def root() -> Dict[str, str]:
    """
    Root discovery endpoint confirming service identity.
    """
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "operational",
        "docs": "/docs" if settings.DEBUG else "disabled",
    }
