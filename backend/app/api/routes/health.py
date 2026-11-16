"""
AutoHeal DevOps — Health Check Router
"""

from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter, status
from app.config import get_settings

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
