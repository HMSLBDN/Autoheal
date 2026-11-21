"""
AutoHeal DevOps — Background Notification Dispatch Tasks
"""

import asyncio
import logging
from typing import Dict, Any
import uuid

from sqlalchemy import select
from app.database import async_session_factory
from app.models.enterprise import NotificationDelivery
from app.services.enterprise.dispatcher import NotificationDispatcher
from app.worker import celery_app

logger = logging.getLogger(__name__)


async def _run_dispatch_delivery(delivery_id_str: str, db: Any = None) -> Dict[str, Any]:
    try:
        deliv_id = uuid.UUID(delivery_id_str)
    except ValueError:
        return {"status": "error", "message": "Invalid delivery UUID"}

    async def _execute(session):
        stmt = select(NotificationDelivery).where(NotificationDelivery.id == deliv_id)
        res = await session.execute(stmt)
        delivery = res.scalars().first()
        if not delivery:
            return {"status": "not_found", "delivery_id": delivery_id_str}

        # Idempotency check: if already delivered or permanently failed, do nothing
        if delivery.status in ["delivered", "permanently_failed", "disabled"]:
            logger.info("Notification delivery %s already in terminal state '%s'.", delivery_id_str, delivery.status)
            return {"status": delivery.status, "delivery_id": delivery_id_str}

        dispatcher = NotificationDispatcher()
        updated_delivery = await dispatcher.retry_delivery(
            db=session,
            organization_id=delivery.organization_id,
            delivery_id=deliv_id,
        )
        if updated_delivery:
            return {
                "status": updated_delivery.status,
                "delivery_id": delivery_id_str,
                "retry_count": updated_delivery.retry_count,
            }
        return {"status": "failed", "delivery_id": delivery_id_str}

    if db is not None:
        return await _execute(db)
    else:
        async with async_session_factory() as session:
            return await _execute(session)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=5)
def dispatch_notification_task(self, delivery_id: str) -> Dict[str, Any]:
    """
    Celery task that dispatches or retries an asynchronous notification delivery.
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run_dispatch_delivery(delivery_id))
        finally:
            loop.close()
    except Exception as exc:
        logger.error("Failed to execute notification delivery task: %s", exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {"status": "failed", "error": str(exc), "delivery_id": delivery_id}
