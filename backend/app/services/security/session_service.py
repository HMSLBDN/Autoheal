"""
AutoHeal DevOps — Enterprise Session Security & Audit Event Service
Manages active sessions, multi-device listing, family-based replay invalidation,
and centralized security audit logging.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import secrets
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from sqlalchemy import select, update, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase10 import UserSession, SecurityAuditEvent
from app.models.user import User

logger = logging.getLogger(__name__)


class SessionService:
    @staticmethod
    def generate_session_token() -> Tuple[str, str]:
        """
        Generates a high-entropy session token and its SHA-256 storage hash.
        Returns: (raw_token, token_hash)
        """
        raw = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return raw, token_hash

    @staticmethod
    async def create_session(
        db: AsyncSession,
        user_id: UUID,
        organization_id: UUID,
        family_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        device_name: Optional[str] = None,
        expires_days: int = 7,
    ) -> Tuple[UserSession, str]:
        """
        Creates an active user session record.
        """
        raw_token, token_hash = SessionService.generate_session_token()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=expires_days)

        session = UserSession(
            user_id=user_id,
            organization_id=organization_id,
            session_token_hash=token_hash,
            family_id=family_id,
            ip_address=ip_address,
            user_agent=user_agent,
            device_name=device_name or SessionService._parse_device_name(user_agent),
            is_active=True,
            expires_at=expires_at,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session, raw_token

    @staticmethod
    async def validate_session(
        db: AsyncSession,
        session_token: str,
    ) -> Optional[UserSession]:
        """
        Validates a session token against active non-expired sessions.
        """
        if not session_token:
            return None
        token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc)

        stmt = select(UserSession).where(
            UserSession.session_token_hash == token_hash,
            UserSession.is_active == True,
            UserSession.expires_at > now,
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def list_active_sessions(
        db: AsyncSession,
        organization_id: UUID,
        user_id: UUID,
        current_session_id: Optional[UUID] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lists all active sessions for a user, indicating which is the current caller session.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(UserSession)
            .where(
                UserSession.organization_id == organization_id,
                UserSession.user_id == user_id,
                UserSession.is_active == True,
                UserSession.expires_at > now,
            )
            .order_by(desc(UserSession.created_at))
        )
        result = await db.execute(stmt)
        sessions = result.scalars().all()

        output = []
        for s in sessions:
            output.append({
                "id": s.id,
                "user_id": s.user_id,
                "organization_id": s.organization_id,
                "family_id": s.family_id,
                "ip_address": s.ip_address,
                "user_agent": s.user_agent,
                "device_name": s.device_name,
                "is_active": s.is_active,
                "expires_at": s.expires_at,
                "created_at": s.created_at,
                "revoked_at": s.revoked_at,
                "revocation_reason": s.revocation_reason,
                "is_current": (s.id == current_session_id) if current_session_id else False,
            })
        return output

    @staticmethod
    async def revoke_session(
        db: AsyncSession,
        organization_id: UUID,
        session_id: UUID,
        reason: str = "User revoked session",
        revoked_by_user_id: Optional[UUID] = None,
    ) -> bool:
        """
        Revokes a specific session. Enforces organization tenant boundary.
        """
        stmt = select(UserSession).where(
            UserSession.id == session_id,
            UserSession.organization_id == organization_id,
            UserSession.is_active == True,
        )
        result = await db.execute(stmt)
        session = result.scalars().first()
        if not session:
            return False

        now = datetime.now(timezone.utc)
        session.is_active = False
        session.revoked_at = now
        session.revocation_reason = reason
        await db.commit()

        await SecurityAuditService.log_event(
            db=db,
            organization_id=organization_id,
            user_id=revoked_by_user_id or session.user_id,
            event_type="session_revoked",
            severity="INFO",
            details={
                "target_session_id": str(session_id),
                "target_user_id": str(session.user_id),
                "reason": reason,
            },
        )
        return True

    @staticmethod
    async def revoke_all_sessions(
        db: AsyncSession,
        organization_id: UUID,
        user_id: UUID,
        keep_session_id: Optional[UUID] = None,
        reason: str = "Revoke all user sessions",
    ) -> int:
        """
        Revokes all active sessions for a user, optionally keeping the current active session.
        """
        now = datetime.now(timezone.utc)
        query = select(UserSession).where(
            UserSession.organization_id == organization_id,
            UserSession.user_id == user_id,
            UserSession.is_active == True,
        )
        if keep_session_id:
            query = query.where(UserSession.id != keep_session_id)

        result = await db.execute(query)
        sessions = result.scalars().all()
        count = len(sessions)

        for s in sessions:
            s.is_active = False
            s.revoked_at = now
            s.revocation_reason = reason

        await db.commit()

        await SecurityAuditService.log_event(
            db=db,
            organization_id=organization_id,
            user_id=user_id,
            event_type="all_sessions_revoked",
            severity="WARNING",
            details={
                "revoked_count": count,
                "kept_session_id": str(keep_session_id) if keep_session_id else None,
                "reason": reason,
            },
        )
        return count

    @staticmethod
    async def handle_family_replay(
        db: AsyncSession,
        organization_id: UUID,
        user_id: UUID,
        family_id: str,
        detected_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        Triggered when a reused or revoked token is attempted.
        Invalidates all sessions in the entire family lineage immediately and logs CRITICAL event.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(UserSession)
            .where(
                UserSession.family_id == family_id,
                UserSession.organization_id == organization_id,
                UserSession.is_active == True,
            )
            .values(
                is_active=False,
                revoked_at=now,
                revocation_reason="Token replay attack detected: entire family invalidated",
            )
        )
        await db.execute(stmt)
        await db.commit()

        await SecurityAuditService.log_event(
            db=db,
            organization_id=organization_id,
            user_id=user_id,
            event_type="token_replay_detected",
            severity="CRITICAL",
            ip_address=detected_ip,
            user_agent=user_agent,
            details={
                "compromised_family_id": family_id,
                "action_taken": "invalidated_entire_token_family",
            },
        )

    @staticmethod
    def _parse_device_name(ua: Optional[str]) -> str:
        if not ua:
            return "Unknown Device"
        ua_lower = ua.lower()
        browser = "Browser"
        if "edg" in ua_lower:
            browser = "Edge"
        elif "chrome" in ua_lower:
            browser = "Chrome"
        elif "firefox" in ua_lower:
            browser = "Firefox"
        elif "safari" in ua_lower:
            browser = "Safari"

        os_name = "Desktop"
        if "windows" in ua_lower:
            os_name = "Windows"
        elif "mac" in ua_lower:
            os_name = "macOS"
        elif "linux" in ua_lower:
            os_name = "Linux"
        elif "android" in ua_lower:
            os_name = "Android"
        elif "iphone" in ua_lower or "ipad" in ua_lower:
            os_name = "iOS"

        return f"{browser} on {os_name}"


class SecurityAuditService:
    @staticmethod
    async def log_event(
        db: AsyncSession,
        organization_id: UUID,
        event_type: str,
        severity: str = "INFO",
        user_id: Optional[UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> SecurityAuditEvent:
        """
        Logs a tamper-evident enterprise security audit event.
        """
        event = SecurityAuditEvent(
            organization_id=organization_id,
            user_id=user_id,
            event_type=event_type,
            severity=severity,
            ip_address=ip_address,
            user_agent=user_agent,
            details_json=details or {},
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event

    @staticmethod
    async def list_events(
        db: AsyncSession,
        organization_id: UUID,
        limit: int = 50,
        severity: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> List[SecurityAuditEvent]:
        """
        Lists security audit events for an organization.
        """
        query = (
            select(SecurityAuditEvent)
            .where(SecurityAuditEvent.organization_id == organization_id)
            .order_by(desc(SecurityAuditEvent.created_at))
            .limit(limit)
        )
        if severity:
            query = query.where(SecurityAuditEvent.severity == severity)
        if event_type:
            query = query.where(SecurityAuditEvent.event_type == event_type)

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_summary(
        db: AsyncSession,
        organization_id: UUID,
    ) -> Dict[str, Any]:
        """
        Computes security audit event summary statistics.
        """
        from sqlalchemy import func

        stmt = (
            select(
                SecurityAuditEvent.severity,
                func.count(SecurityAuditEvent.id),
            )
            .where(SecurityAuditEvent.organization_id == organization_id)
            .group_by(SecurityAuditEvent.severity)
        )
        result = await db.execute(stmt)
        counts = {row[0]: row[1] for row in result.all()}

        recent_stmt = (
            select(SecurityAuditEvent)
            .where(
                SecurityAuditEvent.organization_id == organization_id,
                SecurityAuditEvent.severity.in_(["WARNING", "CRITICAL"]),
            )
            .order_by(desc(SecurityAuditEvent.created_at))
            .limit(10)
        )
        recent_res = await db.execute(recent_stmt)
        recent_suspicious = list(recent_res.scalars().all())

        total = sum(counts.values())
        return {
            "total_events": total,
            "critical_events": counts.get("CRITICAL", 0),
            "warning_events": counts.get("WARNING", 0),
            "recent_suspicious_activities": recent_suspicious,
        }
