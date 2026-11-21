"""
AutoHeal DevOps — Active Session Management & Security Audit API Routes
Provides multi-device session listing, instantaneous revocation,
and organization-wide security audit logging.
"""

import logging
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DatabaseDep, get_current_user, get_current_org, RequireRole
from app.models.organization import Organization
from app.models.user import User
from app.schemas.phase10 import (
    UserSessionResponse,
    RevokeSessionRequest,
    SecurityAuditEventResponse,
    SecurityAuditSummary,
)
from app.services.security.session_service import SessionService, SecurityAuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Sessions & Security Audit"])


@router.get("/sessions", response_model=List[UserSessionResponse])
async def list_user_sessions(
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    db: DatabaseDep = None,
):
    """
    Lists all active sessions across devices for the authenticated user.
    """
    sessions = await SessionService.list_active_sessions(
        db=db,
        organization_id=org.id,
        user_id=user.id,
    )
    return sessions


@router.post("/sessions/{session_id}/revoke")
async def revoke_user_session(
    session_id: uuid.UUID,
    payload: Optional[RevokeSessionRequest] = None,
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    db: DatabaseDep = None,
):
    """
    Terminates a specific active session.
    """
    reason = payload.reason if payload else "User terminated session"
    success = await SessionService.revoke_session(
        db=db,
        organization_id=org.id,
        session_id=session_id,
        reason=reason,
        revoked_by_user_id=user.id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Active session not found or already revoked.")
    return {"status": "success", "message": "Session successfully terminated."}


@router.post("/sessions/revoke-all")
async def revoke_all_user_sessions(
    keep_current: bool = Query(True, description="Keep the calling active session intact"),
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    db: DatabaseDep = None,
):
    """
    Terminates all active sessions for the user across all devices.
    """
    count = await SessionService.revoke_all_sessions(
        db=db,
        organization_id=org.id,
        user_id=user.id,
        reason="User requested sign-out from all devices",
    )
    return {"status": "success", "revoked_sessions_count": count}


@router.get("/security/audit-events", response_model=List[SecurityAuditEventResponse])
async def list_security_audit_events(
    limit: int = Query(50, ge=1, le=200),
    severity: Optional[str] = Query(None, pattern="^(INFO|WARNING|CRITICAL)$"),
    event_type: Optional[str] = None,
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    db: DatabaseDep = None,
):
    """
    Lists tamper-evident security audit events for the organization.
    """
    events = await SecurityAuditService.list_events(
        db=db,
        organization_id=org.id,
        limit=limit,
        severity=severity,
        event_type=event_type,
    )
    return events


@router.get("/security/audit-summary", response_model=SecurityAuditSummary)
async def get_security_audit_summary(
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    db: DatabaseDep = None,
):
    """
    Returns high-level statistics and critical security alerts for the Security Center dashboard.
    """
    summary = await SecurityAuditService.get_summary(
        db=db,
        organization_id=org.id,
    )
    return summary
