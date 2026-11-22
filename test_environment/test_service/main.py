"""
AutoHeal DevOps — Dedicated Isolated Test Application
A harmless, isolated mock microservice designed specifically for controlled chaos and recovery testing.
Has zero connections to AutoHeal databases, credentials, or production services.
"""

from datetime import datetime, timezone
import os
import sys
import time
from fastapi import FastAPI, Response, status

app = FastAPI(title="AutoHeal Dedicated Test Service", version="1.0.0")

STARTUP_TIME = time.time()
HEALTH_STATE = {"status": "healthy", "message": "Service nominal"}


@app.get("/health")
def get_health(response: Response):
    """
    Health check endpoint probed by AutoHeal and Restricted Docker Agent.
    Returns HTTP 200 when healthy, HTTP 503 when degraded.
    """
    current_status = HEALTH_STATE["status"]
    uptime = int(time.time() - STARTUP_TIME)

    if current_status != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": current_status,
            "service": "autoheal_test_service",
            "message": HEALTH_STATE["message"],
            "uptime_seconds": uptime,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "status": "healthy",
        "service": "autoheal_test_service",
        "message": "Operational",
        "uptime_seconds": uptime,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/status")
def get_status():
    """Detailed diagnostic status."""
    return {
        "service": "autoheal_test_service",
        "environment": "isolated_test_sandbox",
        "health": HEALTH_STATE["status"],
        "uptime_seconds": int(time.time() - STARTUP_TIME),
        "pid": os.getpid(),
    }


@app.post("/chaos/crash")
def trigger_crash():
    """Simulates an abrupt process crash by exiting the container process."""
    # Schedule exit shortly to allow returning response
    sys.exit(1)


@app.post("/chaos/degrade")
def trigger_degradation():
    """Simulates service degradation (HTTP 503 on health check)."""
    HEALTH_STATE["status"] = "degraded"
    HEALTH_STATE["message"] = "Simulated connection pool failure"
    return {"message": "Service marked degraded. /health will return HTTP 503."}


@app.post("/chaos/recover")
def trigger_recovery():
    """Manually resets service to healthy state."""
    HEALTH_STATE["status"] = "healthy"
    HEALTH_STATE["message"] = "Service nominal"
    return {"message": "Service marked healthy."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
