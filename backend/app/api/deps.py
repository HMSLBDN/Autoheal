"""
AutoHeal DevOps — API Dependencies & Multi-Tenant Authorization
Provides cryptographic JWT authentication, organization scoping, and RBAC enforcement.
"""

import hashlib
import hmac
from typing import Annotated, Optional, Sequence
import uuid

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.security import decode_access_token
from app.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.services.ticket import sse_ticket_service

settings = get_settings()

DatabaseDep = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    request: Request,
    db: DatabaseDep,
    authorization: Optional[str] = Header(None),
) -> User:
    """
    Authenticates requests via cryptographically signed JWT Bearer tokens or single-use SSE tickets.
    Supports:
      1. Single-use short-lived SSE ticket: ?ticket=<ticket> (hardened, burns upon connection)
      2. Authorization: Bearer <token> header
      3. Legacy query param ?token=<token> (fallback)
    Fails closed on missing, malformed, expired, or invalid credentials (401 Unauthorized).
    Validates user active status in the database.
    """
    token: Optional[str] = None
    ticket_user_id: Optional[str] = None

    if "ticket" in request.query_params:
        ticket_val = request.query_params["ticket"].strip()
        ticket_data = sse_ticket_service.consume_ticket(ticket_val)
        if not ticket_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid, expired, or already consumed event ticket.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        ticket_user_id = ticket_data.get("user_id")
    elif authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif "token" in request.query_params:
        token = request.query_params["token"].strip()

    if not ticket_user_id and not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access this resource.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if ticket_user_id:
        sub = ticket_user_id
    else:
        # Decode and validate JWT access token
        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed token claims.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    try:
        user_uuid = uuid.UUID(sub)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identifier format.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = select(User).options(selectinload(User.organization)).where(User.id == user_uuid)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated. Access denied.",
        )

    return user


async def get_current_org(
    user: Annotated[User, Depends(get_current_user)],
    db: DatabaseDep,
) -> Organization:
    """
    Derives the cryptographically verified Organization context directly
    from the authenticated user. Eliminates any possibility of client-supplied
    tenant tampering.
    """
    if user.organization:
        return user.organization

    result = await db.execute(select(Organization).where(Organization.id == user.organization_id))
    org = result.scalar_one_or_none()
    if not org or not org.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization account is suspended or invalid.",
        )
    return org


class RequireRole:
    """
    RBAC dependency callable ensuring the authenticated user holds one of the required roles.
    Fails closed with 403 Forbidden.
    """
    def __init__(self, allowed_roles: Sequence[str]):
        self.allowed_roles = set(allowed_roles)

    async def __call__(
        self,
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {', '.join(sorted(self.allowed_roles))}. Current role: {user.role}.",
            )
        return user


# Type annotations for route dependencies
UserDep = Annotated[User, Depends(get_current_user)]
OrgDep = Annotated[Organization, Depends(get_current_org)]
RequireAdminDep = Annotated[User, Depends(RequireRole(["admin"]))]
RequireOperatorDep = Annotated[User, Depends(RequireRole(["admin", "operator"]))]
RequireViewerDep = Annotated[User, Depends(RequireRole(["admin", "operator", "viewer"]))]


async def verify_alertmanager_webhook(
    request: Request,
    x_autoheal_signature: Optional[str] = Header(None, alias="X-AutoHeal-Signature"),
    x_alertmanager_secret: Optional[str] = Header(None, alias="X-Alertmanager-Secret"),
    authorization: Optional[str] = Header(None),
) -> bool:
    """
    Validates Alertmanager webhook requests via HMAC-SHA256 signature or shared webhook secret.
    Fails closed with 401 Unauthorized if credentials do not match.
    """
    secret = settings.ALERTMANAGER_HMAC_SECRET.encode("utf-8")

    # 1. Direct secret token verification (X-Alertmanager-Secret or Bearer)
    if x_alertmanager_secret and hmac.compare_digest(x_alertmanager_secret, settings.ALERTMANAGER_HMAC_SECRET):
        return True

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if hmac.compare_digest(token, settings.ALERTMANAGER_HMAC_SECRET):
            return True

    # 2. HMAC-SHA256 payload signature verification
    if x_autoheal_signature:
        sig = x_autoheal_signature.replace("sha256=", "").strip()
        body = await request.body()
        expected_sig = hmac.new(secret, body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected_sig):
            return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized Alertmanager webhook request: Invalid signature or secret.",
        headers={"WWW-Authenticate": "HMAC-SHA256"},
    )


WebhookAuthDep = Annotated[bool, Depends(verify_alertmanager_webhook)]
