"""
AutoHeal DevOps — FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings

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

# Configure Cross-Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


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


@app.get(
    f"{settings.API_V1_STR}/health",
    tags=["Health"],
    summary="Service health probe",
    status_code=status.HTTP_200_OK,
)
async def health_check() -> Dict[str, str]:
    """
    Health probe directly consumed by frontend healthApi.get().
    Contract requires: { "status": str, "timestamp": str }
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": settings.APP_ENV,
        "version": settings.APP_VERSION,
    }
