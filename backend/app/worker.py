"""
AutoHeal DevOps — Celery Distributed Background Worker
Manages scheduled service telemetry collection, asynchronous AI diagnosis,
and policy-governed recovery executions via Redis broker.
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional

from celery import Celery, signals
from celery.schedules import crontab

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

broker_url = settings.CELERY_BROKER_URL or settings.REDIS_URL
result_backend = settings.CELERY_RESULT_BACKEND or settings.REDIS_URL

celery_app = Celery(
    "autoheal_worker",
    broker=broker_url,
    backend=result_backend,
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

def get_redis_ssl_options(settings_obj: Any, url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Builds hardened SSL/TLS connection options for Celery Redis broker and backend.
    Enforces certificate verification, hostname checking, and CA validation.
    """
    target_url = url or getattr(settings_obj, "CELERY_BROKER_URL", None) or getattr(settings_obj, "REDIS_URL", None)
    if not target_url or not target_url.startswith("rediss://"):
        return None

    import ssl
    import os

    cert_reqs_map = {
        "required": ssl.CERT_REQUIRED,
        "optional": ssl.CERT_OPTIONAL,
        "none": ssl.CERT_NONE,
    }

    cert_reqs_setting = getattr(settings_obj, "REDIS_SSL_CERT_REQS", "required")
    check_hostname_setting = getattr(settings_obj, "REDIS_SSL_CHECK_HOSTNAME", True)
    app_env = getattr(settings_obj, "APP_ENV", "development")

    if app_env in ("production", "staging") and cert_reqs_setting == "none":
        raise ValueError(
            "Disabling Redis TLS certificate verification ('none') is strictly prohibited "
            "in production or staging environments."
        )

    if app_env in ("production", "staging") and not check_hostname_setting:
        raise ValueError(
            "Disabling Redis TLS hostname verification is strictly prohibited "
            "in production or staging environments."
        )

    cert_reqs = cert_reqs_map.get(cert_reqs_setting, ssl.CERT_REQUIRED)

    ssl_options: Dict[str, Any] = {
        "ssl_cert_reqs": cert_reqs,
        "ssl_check_hostname": check_hostname_setting,
    }

    ca_certs = getattr(settings_obj, "REDIS_SSL_CA_CERTS", None)
    if ca_certs:
        if not os.path.isfile(ca_certs):
            raise FileNotFoundError(f"Configured REDIS_SSL_CA_CERTS file not found: {ca_certs}")
        ssl_options["ssl_ca_certs"] = ca_certs

    certfile = getattr(settings_obj, "REDIS_SSL_CERTFILE", None)
    if certfile:
        if not os.path.isfile(certfile):
            raise FileNotFoundError(f"Configured REDIS_SSL_CERTFILE file not found: {certfile}")
        ssl_options["ssl_certfile"] = certfile

    keyfile = getattr(settings_obj, "REDIS_SSL_KEYFILE", None)
    if keyfile:
        if not os.path.isfile(keyfile):
            raise FileNotFoundError(f"Configured REDIS_SSL_KEYFILE file not found: {keyfile}")
        ssl_options["ssl_keyfile"] = keyfile

    return ssl_options


# Support managed cloud Redis with verified TLS (rediss://)
ssl_options = get_redis_ssl_options(settings, broker_url)
if ssl_options:
    celery_app.conf.update(
        broker_use_ssl=ssl_options,
        redis_backend_use_ssl=ssl_options,
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
