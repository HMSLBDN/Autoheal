"""
Restricted Docker Agent — Execution Audit Logging Module
Maintains a bounded in-memory circular buffer of execution audit events.
NOTE: In-memory buffers are bounded (maxlen=500) and ephemeral across process restarts.
For production compliance, events are simultaneously emitted to structured logs.
Secrets, auth tokens, and private keys are NEVER logged.
"""

from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentAuditLogger:
    """
    Maintains a bounded in-memory circular buffer of execution audit events.
    """

    def __init__(self, max_records: int = 500):
        self._buffer: deque = deque(maxlen=max_records)

    def record_event(
        self,
        event_type: str,
        action_id: str,
        target_container: str,
        action_type: str,
        status: str,
        exit_code: int,
        duration_ms: int,
        evidence_hash: str,
        details: str = "",
        correlation_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        is_mocked: bool = False,
    ) -> Dict[str, Any]:
        """
        Records an audit event in memory and logs via structured logger.
        """
        now = datetime.now(timezone.utc)
        record = {
            "timestamp": now.isoformat(),
            "event_type": event_type,
            "action_id": action_id,
            "target_container": target_container,
            "action_type": action_type,
            "status": status,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "evidence_hash": evidence_hash,
            "details": details,
            "correlation_id": correlation_id or "none",
            "client_ip": client_ip or "internal",
            "is_mocked": is_mocked,
        }
        self._buffer.append(record)

        logger.info(
            "AGENT_AUDIT: event=%s action_id=%s container=%s action=%s status=%s code=%d hash=%s",
            event_type,
            action_id,
            target_container,
            action_type,
            status,
            exit_code,
            evidence_hash[:16] if evidence_hash else "none",
        )
        return record

    def get_recent_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns recent audit logs up to limit."""
        bounded = max(1, min(limit, 200))
        records = list(self._buffer)
        return records[-bounded:]

    def clear(self) -> None:
        """Clears audit buffer (used in unit testing)."""
        self._buffer.clear()


audit_logger = AgentAuditLogger()
