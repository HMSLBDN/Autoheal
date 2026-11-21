"""
AutoHeal DevOps — Background Escalation Evaluation Tasks
Periodically evaluates unacknowledged incidents against active escalation policies.
"""

import asyncio
import logging
from typing import Dict, Any, List

from sqlalchemy import select
from app.database import async_session_factory
from app.models.organization import Organization
from app.services.enterprise.collaboration import IncidentCollaborationEngine
from app.worker import celery_app

logger = logging.getLogger(__name__)


async def _run_escalation_evaluations() -> Dict[str, Any]:
    collab_engine = IncidentCollaborationEngine()
    total_triggered = 0

    async with async_session_factory() as session:
        # Fetch all organizations
        org_q = select(Organization)
        org_res = await session.execute(org_q)
        orgs = org_res.scalars().all()

        for org in orgs:
            try:
                events = await collab_engine.evaluate_escalations(db=session, organization_id=org.id)
                total_triggered += len(events)
            except Exception as e:
                logger.error("Error evaluating escalations for organization %s: %s", org.id, e)

    return {"status": "success", "total_escalations_triggered": total_triggered}


@celery_app.task(bind=True, max_retries=1, default_retry_delay=10)
def evaluate_escalation_policies_task(self) -> Dict[str, Any]:
    """
    Celery task that scans active organizations and escalates unacknowledged incidents.
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run_escalation_evaluations())
        finally:
            loop.close()
    except Exception as exc:
        logger.error("Failed to run escalation evaluation task: %s", exc)
        return {"status": "error", "message": str(exc)}
