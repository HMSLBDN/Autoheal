"""
AutoHeal DevOps — Celery Distributed Background Worker
Manages scheduled service telemetry collection, asynchronous AI diagnosis,
and policy-governed recovery executions via Redis broker.
"""

import asyncio
import logging
import os
from typing import Any, Dict

from celery import Celery
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
    task_time_limit=120,          # Hard task limit
    task_soft_time_limit=90,      # Soft task limit
    task_acks_late=True,          # Acknowledge after task finishes for resilience
    worker_prefetch_multiplier=1, # Fair dispatching
    task_default_retry_delay=5,
    task_max_retries=3,
)

# Scheduled Periodic Monitoring Jobs (Celery Beat)
celery_app.conf.beat_schedule = {
    "periodic-service-monitoring-cycle": {
        "task": "app.tasks.monitoring.monitor_services_task",
        "schedule": float(settings.METRIC_SCRAPE_INTERVAL_SECONDS),
        "options": {"expires": 10},
    },
}
