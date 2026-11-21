"""
AutoHeal DevOps — API Router Registry
Assembles all sub-routers into /api/v1 router
"""

from fastapi import APIRouter

from app.api.routes import (
    agents,
    alerts,
    analytics,
    auth,
    collaboration,
    demo,
    escalations,
    events,
    health,
    incidents,
    intelligence,
    notifications,
    policies,
    recoveries,
    releases,
    services,
    settings,
    timeline,
    webhooks,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(agents.router)
api_router.include_router(policies.router)
api_router.include_router(alerts.router)
api_router.include_router(health.router)
api_router.include_router(services.router)
api_router.include_router(incidents.router)
api_router.include_router(recoveries.router)
api_router.include_router(analytics.router)
api_router.include_router(intelligence.router)
api_router.include_router(events.router)
api_router.include_router(settings.router)
api_router.include_router(notifications.router)
api_router.include_router(webhooks.router)
api_router.include_router(collaboration.router)
api_router.include_router(escalations.router)
api_router.include_router(releases.router)
api_router.include_router(timeline.router)
api_router.include_router(demo.router)
