"""
AutoHeal DevOps — Celery Distributed Background Worker
Manages scheduled service telemetry collection, asynchronous AI diagnosis,
and policy-governed recovery executions via Redis broker.
"""

import asyncio
import logging
import os
from typing import Any, Dict

from celery import Celery, signals
from celery.schedules import crontab

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

celery_app = Celery(
    "autoheal_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.monitoring",
        "app.tasks.alerts",
        "app.tasks.diagnosis",
        "app.tasks.recovery",
    ],
)

# Eagerly import tasks to register decorators
import app.tasks.monitoring
import app.tasks.alerts
import app.tasks.diagnosis
import app.tasks.recovery

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=180,                   # Hard task limit (3 minutes)
    task_soft_time_limit=120,              # Soft task limit (2 minutes)
    task_acks_late=True,                   # Acknowledge after task finishes for resilience
    task_reject_on_worker_lost=True,       # Re-queue tasks if worker process unexpectedly dies
    broker_connection_retry_on_startup=True, # Resilient connection retry on boot
    worker_prefetch_multiplier=1,          # Fair dispatching, prevent worker starvation
    task_default_retry_delay=5,
    task_max_retries=3,
)


@signals.task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, traceback=None, einfo=None, **extra):
    """
    Dead-letter logging for tasks that encounter unhandled exceptions or exhaust retry limits.
    """
    logger.error(
        "[CELERY_DEAD_LETTER] Task %s (ID: %s) failed with exception: %s. Args: %s",
        getattr(sender, "name", "unknown_task"),
        task_id,
        exception,
        args,
    )


@signals.worker_shutting_down.connect
def on_worker_shutdown(sig=None, how=None, exitcode=None, **extra):
    """
    Graceful shutdown logging when worker receives SIGTERM or SIGINT.
    """
    logger.info("[CELERY_WORKER_SHUTDOWN] Worker gracefully completing in-flight tasks and draining queue (signal=%s, code=%s)", sig, exitcode)

# Scheduled Periodic Monitoring Jobs (Celery Beat)
celery_app.conf.beat_schedule = {
    "periodic-service-monitoring-cycle": {
        "task": "app.tasks.monitoring.monitor_services_task",
        "schedule": float(settings.METRIC_SCRAPE_INTERVAL_SECONDS),
        "options": {"expires": 10},
    },
}
