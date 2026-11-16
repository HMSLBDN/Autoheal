"""
AutoHeal DevOps — Background Recovery Execution & Verification Tasks
"""

import asyncio
import logging
from typing import Dict, Any

from app.database import async_session_factory
from app.services.recovery.executor import RecoveryExecutor
from app.worker import celery_app

logger = logging.getLogger(__name__)


async def _run_recovery(recovery_id: str, simulated_healthy: bool = True) -> Dict[str, Any]:
    async with async_session_factory() as session:
        executor = RecoveryExecutor()
        recovery = await executor.execute_recovery(
            db=session,
            recovery_id=recovery_id,
            simulated_outcome_healthy=simulated_healthy,
        )
        return {
            "status": "success",
            "recovery_id": recovery.id,
            "action": recovery.action,
            "recovery_status": recovery.status,
            "verification": recovery.verification,
            "summary": recovery.result.summary if recovery.result else None,
        }


@celery_app.task(bind=True, max_retries=1, default_retry_delay=5)
def execute_recovery_task(self, recovery_id: str, simulated_healthy: bool = True) -> Dict[str, Any]:
    """
    Celery task that executes an approved recovery action and coordinates post-recovery verification.
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run_recovery(recovery_id, simulated_healthy))
        finally:
            loop.close()
    except Exception as exc:
        logger.error("Recovery execution task failed for '%s': %s", recovery_id, exc)
        raise self.retry(exc=exc)
