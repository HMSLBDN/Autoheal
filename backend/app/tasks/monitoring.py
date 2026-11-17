"""
AutoHeal DevOps — Background Telemetry Monitoring Tasks
"""

import asyncio
import logging
from typing import Dict, Any

from app.database import async_session_factory, engine
from app.services.monitoring import MonitoringService
from app.worker import celery_app

logger = logging.getLogger(__name__)


async def _run_monitoring() -> Dict[str, Any]:
    async with async_session_factory() as session:
        monitoring_service = MonitoringService()
        metrics = await monitoring_service.run_monitoring_cycle(session)
        return {
            "status": "success",
            "services_scraped": len(metrics),
            "timestamp": str(metrics[0].sampled_at) if metrics else None,
        }


@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def monitor_services_task(self) -> Dict[str, Any]:
    """
    Celery task that executes an automated telemetry collection cycle.
    Updates service status and stores time-series metric samples in PostgreSQL.
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run_monitoring())
        finally:
            try:
                loop.run_until_complete(engine.dispose())
            except Exception:
                pass
            loop.close()
    except Exception as exc:
        logger.error("Monitoring task failed: %s. Retrying...", exc)
        raise self.retry(exc=exc)
