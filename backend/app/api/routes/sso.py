"""
AutoHeal DevOps — Enterprise Single Sign-On (SSO) API Routes
Implements OIDC/OAuth 2.0 PKCE Provider Management, Authorization Flow, and Token Callback.
"""

import logging
from typing import List
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DatabaseDep, get_current_user, get_current_org, RequireRole
from app.core.security import encrypt_secret, mask_secret
from app.models.phase10 import IdentityProviderConfig
from app.models.organization import Organization
from app.models.user import User
from app.schemas.phase10 import (
    IdentityProviderCreate,
    IdentityProviderUpdate,
    IdentityProviderResponse,
    SsoAuthorizeRequest,
    SsoAuthorizeResponse,
    SsoCallbackRequest,
    SsoCallbackResponse,
)
from app.services.security.sso_service import SsoService
from app.services.security.session_service import SecurityAuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/sso", tags=["Enterprise SSO"])


@router.get("/providers", response_model=List[IdentityProviderResponse])
async def list_identity_providers(
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    db: DatabaseDep = None,
):
    """
    Lists all configured SSO Identity Providers for the caller's organization.
    Client secrets are masked for safety.
    """
    stmt = (
        select(IdentityProviderConfig)
        .where(IdentityProviderConfig.organization_id == org.id)
        .order_by(desc(IdentityProviderConfig.created_at))
    )
    res = await db.execute(stmt)
    providers = res.scalars().all()

    return [
        IdentityProviderResponse(
            id=p.id,
            organization_id=p.organization_id,
            name=p.name,
            idp_type=p.idp_type,
            issuer_url=p.issuer_url,
            client_id=p.client_id,
            client_secret_masked=mask_secret(p.client_secret_encrypted),
            metadata_url=p.metadata_url,
            jwks_url=p.jwks_url,
            authorization_endpoint=p.authorization_endpoint,
            token_endpoint=p.token_endpoint,
            userinfo_endpoint=p.userinfo_endpoint,
            role_mapping_json=p.role_mapping_json or {},
            allowed_domains=p.allowed_domains or [],
            is_active=p.is_active,
            is_enforced=p.is_enforced,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in providers
    ]


@router.post(
    "/providers",
    response_model=IdentityProviderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RequireRole(["admin"]))],
)
async def create_identity_provider(
    payload: IdentityProviderCreate,
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    db: DatabaseDep = None,
):
    """
    Registers a new SSO Identity Provider with encrypted client secret (Admin only).
    """
    encrypted_secret = encrypt_secret(payload.client_secret)

    provider = IdentityProviderConfig(
        organization_id=org.id,
        name=payload.name,
        idp_type=payload.idp_type,
        issuer_url=payload.issuer_url,
        client_id=payload.client_id,
        client_secret_encrypted=encrypted_secret,
        metadata_url=payload.metadata_url,
        jwks_url=payload.jwks_url,
        authorization_endpoint=payload.authorization_endpoint,
        token_endpoint=payload.token_endpoint,
        userinfo_endpoint=payload.userinfo_endpoint,
        role_mapping_json=payload.role_mapping_json,
        allowed_domains=payload.allowed_domains,
        is_active=payload.is_active,
        is_enforced=payload.is_enforced,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)

    await SecurityAuditService.log_event(
        db=db,
        organization_id=org.id,
        user_id=user.id,
        event_type="idp_configured",
        severity="INFO",
        details={
            "provider_id": str(provider.id),
            "provider_name": provider.name,
            "issuer_url": provider.issuer_url,
        },
    )

    return IdentityProviderResponse(
        id=provider.id,
        organization_id=provider.organization_id,
        name=provider.name,
        idp_type=provider.idp_type,
        issuer_url=provider.issuer_url,
        client_id=provider.client_id,
        client_secret_masked=mask_secret(payload.client_secret),
        metadata_url=provider.metadata_url,
        jwks_url=provider.jwks_url,
        authorization_endpoint=provider.authorization_endpoint,
        token_endpoint=provider.token_endpoint,
        userinfo_endpoint=provider.userinfo_endpoint,
        role_mapping_json=provider.role_mapping_json or {},
        allowed_domains=provider.allowed_domains or [],
        is_active=provider.is_active,
        is_enforced=provider.is_enforced,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


@router.put(
    "/providers/{provider_id}",
    response_model=IdentityProviderResponse,
    dependencies=[Depends(RequireRole(["admin"]))],
)
async def update_identity_provider(
    provider_id: uuid.UUID,
    payload: IdentityProviderUpdate,
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    db: DatabaseDep = None,
):
    """
    Updates an existing SSO Identity Provider configuration (Admin only).
    """
    stmt = select(IdentityProviderConfig).where(
        IdentityProviderConfig.id == provider_id,
        IdentityProviderConfig.organization_id == org.id,
    )
    res = await db.execute(stmt)
    provider = res.scalars().first()
    if not provider:
        raise HTTPException(status_code=404, detail="Identity provider not found.")

    if payload.name is not None:
        provider.name = payload.name
    if payload.client_secret is not None:
        provider.client_secret_encrypted = encrypt_secret(payload.client_secret)
    if payload.metadata_url is not None:
        provider.metadata_url = payload.metadata_url
    if payload.jwks_url is not None:
        provider.jwks_url = payload.jwks_url
    if payload.authorization_endpoint is not None:
        provider.authorization_endpoint = payload.authorization_endpoint
    if payload.token_endpoint is not None:
        provider.token_endpoint = payload.token_endpoint
    if payload.userinfo_endpoint is not None:
        provider.userinfo_endpoint = payload.userinfo_endpoint
    if payload.role_mapping_json is not None:
        provider.role_mapping_json = payload.role_mapping_json
    if payload.allowed_domains is not None:
        provider.allowed_domains = payload.allowed_domains
    if payload.is_active is not None:
        provider.is_active = payload.is_active
    if payload.is_enforced is not None:
        provider.is_enforced = payload.is_enforced

    await db.commit()
    await db.refresh(provider)

    return IdentityProviderResponse(
        id=provider.id,
        organization_id=provider.organization_id,
        name=provider.name,
        idp_type=provider.idp_type,
        issuer_url=provider.issuer_url,
        client_id=provider.client_id,
        client_secret_masked=mask_secret(provider.client_secret_encrypted),
        metadata_url=provider.metadata_url,
        jwks_url=provider.jwks_url,
        authorization_endpoint=provider.authorization_endpoint,
        token_endpoint=provider.token_endpoint,
        userinfo_endpoint=provider.userinfo_endpoint,
        role_mapping_json=provider.role_mapping_json or {},
        allowed_domains=provider.allowed_domains or [],
        is_active=provider.is_active,
        is_enforced=provider.is_enforced,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


@router.delete(
    "/providers/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequireRole(["admin"]))],
)
async def delete_identity_provider(
    provider_id: uuid.UUID,
    org: Organization = Depends(get_current_org),
    user: User = Depends(get_current_user),
    db: DatabaseDep = None,
):
    """
    Deletes an SSO Identity Provider configuration (Admin only).
    """
    stmt = select(IdentityProviderConfig).where(
        IdentityProviderConfig.id == provider_id,
        IdentityProviderConfig.organization_id == org.id,
    )
    res = await db.execute(stmt)
    provider = res.scalars().first()
    if not provider:
        raise HTTPException(status_code=404, detail="Identity provider not found.")

    await db.delete(provider)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/authorize", response_model=SsoAuthorizeResponse)
async def initiate_sso_authorization(
    payload: SsoAuthorizeRequest,
    db: DatabaseDep = None,
):
    """
    Initiates OIDC login flow by generating PKCE verifier/challenge and authorization redirect URL.
    """
    stmt = select(IdentityProviderConfig).where(
        IdentityProviderConfig.id == payload.provider_id,
        IdentityProviderConfig.is_active == True,
    )
    res = await db.execute(stmt)
    provider = res.scalars().first()
    if not provider:
        raise HTTPException(status_code=404, detail="Active identity provider not found.")

    code_verifier, code_challenge = SsoService.generate_pkce_pair()
    import secrets
    state = payload.state or secrets.token_urlsafe(32)

    auth_url = SsoService.build_authorization_url(
        provider=provider,
        redirect_uri=payload.redirect_uri,
        state=state,
        code_challenge=code_challenge,
    )

    return SsoAuthorizeResponse(
        authorization_url=auth_url,
        state=state,
        code_verifier=code_verifier,
    )


@router.post("/callback", response_model=SsoCallbackResponse)
async def handle_sso_callback(
    payload: SsoCallbackRequest,
    request: Request,
    db: DatabaseDep = None,
):
    """
    Completes the OIDC/OAuth 2.0 PKCE flow, provisions/links user account,
    creates active session, and returns signed access & refresh tokens.
    """
    stmt = select(IdentityProviderConfig).where(
        IdentityProviderConfig.id == payload.provider_id,
        IdentityProviderConfig.is_active == True,
    )
    res = await db.execute(stmt)
    provider = res.scalars().first()
    if not provider:
        raise HTTPException(status_code=404, detail="Active identity provider not found.")

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        user, access_token, refresh_token, session_id = await SsoService.process_sso_callback(
            db=db,
            provider=provider,
            code=payload.code,
            code_verifier=payload.code_verifier,
            redirect_uri=payload.redirect_uri,
            ip_address=ip,
            user_agent=ua,
        )
    except ValueError as e:
        logger.warning("SSO Callback failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

    return SsoCallbackResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
        role=user.role,
        organization_id=user.organization_id,
        session_id=session_id,
    )
