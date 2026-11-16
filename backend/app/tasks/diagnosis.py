"""
AutoHeal DevOps — Asynchronous AI Diagnosis Tasks
"""

import asyncio
import logging
from typing import Dict, Any
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session_factory
from app.models.incident import Incident, IncidentEvent, IncidentEvidence
from app.models.service import Service
from app.services.ai.factory import get_ai_provider
from app.worker import celery_app

logger = logging.getLogger(__name__)


async def _run_diagnosis(incident_id: str) -> Dict[str, Any]:
    async with async_session_factory() as session:
        stmt = select(Incident).options(selectinload(Incident.service)).where(Incident.id == incident_id)
        res = await session.execute(stmt)
        incident = res.scalar_one_or_none()

        if not incident:
            logger.warning("Incident '%s' not found for diagnosis.", incident_id)
            return {"status": "not_found", "incident_id": incident_id}

        ai_provider = get_ai_provider()
        context = {
            "service_name": incident.service_name,
            "alert_name": incident.title,
            "severity": incident.severity,
            "error_rate": incident.error_rate,
            "description": incident.title,
        }

        diagnosis = await ai_provider.diagnose(context)

        incident.probable_cause = diagnosis.probable_root_cause
        incident.recommended_action = diagnosis.recommended_action
        incident.recovery_status = "Approval required"

        session.add(IncidentEvidence(
            incident_id=incident.id,
            kind="log",
            title="AI Root Cause Analysis",
            detail=f"{diagnosis.probable_root_cause} (Risk: {diagnosis.risk_level})",
            timestamp="Just now",
        ))

        session.add(IncidentEvent(
            incident_id=incident.id,
            label="AI Diagnosis Generated",
            detail=f"Recommended: {diagnosis.recommended_action} (Confidence: {int(diagnosis.confidence_score * 100)}%)",
            timestamp="Just now",
            tone="neutral",
        ))

        await session.commit()

        return {
            "status": "success",
            "incident_id": incident.id,
            "probable_cause": incident.probable_cause,
            "recommended_action": incident.recommended_action,
        }


@celery_app.task(bind=True, max_retries=2, default_retry_delay=3)
def diagnose_incident_task(self, incident_id: str) -> Dict[str, Any]:
    """
    Celery task that executes asynchronous AI diagnosis for an incident.
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run_diagnosis(incident_id))
        finally:
            loop.close()
    except Exception as exc:
        logger.error("AI diagnosis task for '%s' failed: %s", incident_id, exc)
        raise self.retry(exc=exc)
