"""
AutoHeal DevOps — API Router Registry
Assembles all sub-routers into /api/v1 router
"""

from fastapi import APIRouter

from app.api.routes import alerts, analytics, auth, demo, events, health, incidents, recoveries, services, settings

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(alerts.router)
api_router.include_router(health.router)
api_router.include_router(services.router)
api_router.include_router(incidents.router)
api_router.include_router(recoveries.router)
api_router.include_router(analytics.router)
api_router.include_router(events.router)
api_router.include_router(settings.router)
api_router.include_router(demo.router)
