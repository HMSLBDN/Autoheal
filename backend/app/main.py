"""
AutoHeal DevOps — FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings
from app.core.logging import RequestTracingMiddleware

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifecycle management (startup and graceful shutdown).
    """
    # Startup: Initialize connection pools, verify health of upstream services
    yield
    # Shutdown: Cleanly close background executors, Redis connections, DB pools


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
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Mount API v1 router registry
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get(
    "/metrics",
    response_class=PlainTextResponse,
    include_in_schema=False,
    summary="Prometheus exposition metrics endpoint",
)
async def metrics() -> PlainTextResponse:
    """Exposes application runtime telemetry metrics for Prometheus scraping."""
    content = (
        "# HELP autoheal_api_up Service operational status gauge\n"
        "# TYPE autoheal_api_up gauge\n"
        "autoheal_api_up 1\n"
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
