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
    yield
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
    """
    request_id = getattr(request.state, "request_id", None) or "unknown"
    logger.exception("Unhandled server exception processing request %s: %s", request_id, exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"An unexpected internal error occurred. Please quote request ID {request_id} to support.",
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
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
