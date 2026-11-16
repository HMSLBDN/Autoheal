"""
AutoHeal DevOps — API Dependencies & Multi-Tenant Organization Scoping
"""

from typing import Annotated, Optional
import uuid

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.organization import Organization

settings = get_settings()

DatabaseDep = Annotated[AsyncSession, Depends(get_db)]


async def get_current_org(
    request: Request,
    db: DatabaseDep,
    authorization: Optional[str] = Header(None),
) -> Organization:
    """
    Resolves the trusted Organization context for multi-tenant data isolation.
    Fails closed: Any unauthenticated request without a validated trusted credential
    is rejected with 401 Unauthorized.
    Client-supplied organization IDs are NEVER accepted as proof of authorization.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access organization resources.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1].strip()

    # In Step 3 (prior to full Step 4 User JWT auth flow), support the trusted system/admin secret
    # or token validation. If invalid, fail closed immediately.
    if token != settings.SECRET_KEY:
        # In Step 4 this will decode JWT and look up user's organization_id
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Resolve default organization from DB
    result = await db.execute(
        select(Organization).where(Organization.slug == settings.DEFAULT_ORGANIZATION_SLUG)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configured organization context is not provisioned in database.",
        )

    return org


OrgDep = Annotated[Organization, Depends(get_current_org)]
