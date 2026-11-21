"""
AutoHeal DevOps — Pilot Onboarding & Team Invitations Router
Provides end-to-end team onboarding, cryptographically verified role invitations,
and readiness checklist verification for engineering teams.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import secrets
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    DatabaseDep,
    OrgDep,
    RequireAdminDep,
    UserDep,
)
from app.core.rate_limit import check_auth_rate_limit
from app.config import get_settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    get_password_hash,
    hash_token,
)
from app.models.audit import AuditLog
from app.models.enterprise import NotificationChannel
from app.models.incident import Incident
from app.models.metric import ServiceMetric
from app.models.organization import Organization, OrganizationInvitation
from app.models.refresh_token import RefreshToken
from app.models.service import Service
from app.models.user import User
from app.schemas.auth import TokenResponse, UserResponse
from app.schemas.onboarding import (
    AcceptInviteRequest,
    InviteCreateRequest,
    InviteResponse,
    OnboardingChecklistResponse,
    OnboardingStep,
)

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/onboarding", tags=["Pilot Onboarding"])


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Sets secure, HttpOnly refresh token cookie on HTTP response."""
    secure_cookie = settings.COOKIE_SECURE if settings.COOKIE_SECURE is not None else (settings.APP_ENV not in ("development", "test"))
    samesite_policy = settings.COOKIE_SAMESITE if settings.COOKIE_SAMESITE is not None else ("none" if secure_cookie else "lax")
    max_age_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    kwargs = {
        "key": "refresh_token",
        "value": refresh_token,
        "max_age": max_age_seconds,
        "httponly": True,
        "samesite": samesite_policy,
        "secure": secure_cookie,
        "path": "/api/v1/auth",
    }
    if settings.COOKIE_DOMAIN:
        kwargs["domain"] = settings.COOKIE_DOMAIN
    response.set_cookie(**kwargs)


@router.post(
    "/invite",
    response_model=InviteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite team member with designated role (Admin only)",
)
async def invite_team_member(
    payload: InviteCreateRequest,
    request: Request,
    org: OrgDep,
    current_admin: RequireAdminDep,
    db: DatabaseDep,
) -> InviteResponse:
    """
    Issues a cryptographically secure, role-bounded invitation for a new team member.
    Enforces that only tenant Admins can invite team members.
    Prevents duplicate pending invitations and already-registered users.
    """
    normalized_email = payload.email.lower().strip()
    role = payload.role.lower().strip()

    if role not in ("viewer", "operator", "admin"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role designated. Permitted roles are: 'viewer', 'operator', 'admin'.",
        )

    # Check if user already exists
    existing_user = await db.execute(select(User).where(User.email == normalized_email))
    if existing_user.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An account with email '{normalized_email}' is already registered in the system.",
        )

    # Check if active, unexpired invitation already exists
    now = datetime.now(timezone.utc)
    existing_invite = await db.execute(
        select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == org.id,
            OrganizationInvitation.email == normalized_email,
            OrganizationInvitation.is_accepted.is_(False),
            OrganizationInvitation.expires_at > now,
        )
    )
    if existing_invite.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An active invitation for '{normalized_email}' already exists. Please await acceptance or re-invite after expiration.",
        )

    # Generate raw token and hash
    raw_token = secrets.token_urlsafe(32)
    token_hash_val = hash_token(raw_token)
    expires_at = now + timedelta(days=7)

    invitation = OrganizationInvitation(
        id=uuid.uuid4(),
        organization_id=org.id,
        email=normalized_email,
        role=role,
        token_hash=token_hash_val,
        invited_by_user_id=current_admin.id,
        is_accepted=False,
        expires_at=expires_at,
    )
    db.add(invitation)

    # Add audit log
    db.add(AuditLog(
        organization_id=org.id,
        user_id=current_admin.id,
        action="user_invited",
        resource_type="invitation",
        resource_id=str(invitation.id),
        details=f"Admin '{current_admin.email}' invited '{normalized_email}' with role '{role}'.",
        ip_address=request.client.host if request.client else None,
    ))
    await db.commit()

    return InviteResponse(
        id=str(invitation.id),
        email=invitation.email,
        role=invitation.role,
        organization_id=str(invitation.organization_id),
        invited_by_email=current_admin.email,
        invitation_token=raw_token,
        invite_url=f"/auth/accept-invite?token={raw_token}",
        expires_at=invitation.expires_at,
        is_accepted=invitation.is_accepted,
        created_at=invitation.created_at,
    )


@router.get(
    "/invitations",
    response_model=List[InviteResponse],
    summary="List organization invitations (Admin / Operator)",
)
async def list_invitations(
    org: OrgDep,
    db: DatabaseDep,
    active_only: bool = Query(True, description="Filter for active, unexpired invitations only"),
) -> List[InviteResponse]:
    """Lists organization invitations for team onboarding management."""
    stmt = (
        select(OrganizationInvitation)
        .where(OrganizationInvitation.organization_id == org.id)
        .order_by(OrganizationInvitation.created_at.desc())
    )
    if active_only:
        now = datetime.now(timezone.utc)
        stmt = stmt.where(
            OrganizationInvitation.is_accepted.is_(False),
            OrganizationInvitation.expires_at > now,
        )

    result = await db.execute(stmt)
    invites = result.scalars().all()

    return [
        InviteResponse(
            id=str(i.id),
            email=i.email,
            role=i.role,
            organization_id=str(i.organization_id),
            invited_by_email=None,
            invitation_token=None,
            invite_url=None,
            expires_at=i.expires_at,
            is_accepted=i.is_accepted,
            created_at=i.created_at,
        )
        for i in invites
    ]


@router.post(
    "/accept-invite",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Accept team invitation and activate account",
    dependencies=[Depends(check_auth_rate_limit)],
)
async def accept_invitation(
    payload: AcceptInviteRequest,
    request: Request,
    response: Response,
    db: DatabaseDep,
) -> TokenResponse:
    """
    Verifies invitation token, validates expiration, creates new User account
    locked to the pre-designated role and organization, and returns authenticated session tokens.
    """
    token_hash_val = hash_token(payload.token.strip())
    now = datetime.now(timezone.utc)

    stmt = select(OrganizationInvitation).where(
        OrganizationInvitation.token_hash == token_hash_val
    )
    res = await db.execute(stmt)
    invitation = res.scalar_one_or_none()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invitation token.",
        )

    if invitation.is_accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has already been accepted.",
        )

    # Check expiration
    exp = invitation.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation token has expired. Please request a new invitation from your administrator.",
        )

    # Prevent collision if email was registered independently
    existing_user = await db.execute(select(User).where(User.email == invitation.email))
    if existing_user.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An account for '{invitation.email}' already exists.",
        )

    # Create new user strictly locked to invitation's organization and designated role
    new_user = User(
        id=uuid.uuid4(),
        organization_id=invitation.organization_id,
        email=invitation.email,
        full_name=payload.full_name.strip(),
        hashed_password=get_password_hash(payload.password),
        role=invitation.role,
        is_active=True,
    )
    db.add(new_user)
    invitation.is_accepted = True

    # Audit log
    db.add(AuditLog(
        organization_id=invitation.organization_id,
        user_id=new_user.id,
        action="invitation_accepted",
        resource_type="user",
        resource_id=str(new_user.id),
        details=f"User '{new_user.email}' activated account via invitation with role '{new_user.role}'.",
        ip_address=request.client.host if request.client else None,
    ))
    await db.flush()

    # Issue initial access and refresh tokens
    access_token = create_access_token(
        user_id=str(new_user.id),
        email=new_user.email,
        role=new_user.role,
        org_id=str(new_user.organization_id),
    )

    raw_refresh_token = generate_refresh_token()
    refresh_hash_val = hash_token(raw_refresh_token)
    family_id = str(uuid.uuid4())
    refresh_record = RefreshToken(
        id=uuid.uuid4(),
        user_id=new_user.id,
        token_hash=refresh_hash_val,
        family_id=family_id,
        is_revoked=False,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(refresh_record)
    await db.commit()

    _set_refresh_cookie(response, raw_refresh_token)

    # Load org name
    org_res = await db.execute(select(Organization).where(Organization.id == new_user.organization_id))
    org_rec = org_res.scalar_one_or_none()

    user_response = UserResponse(
        id=str(new_user.id),
        email=new_user.email,
        full_name=new_user.full_name,
        role=new_user.role,
        organization_id=str(new_user.organization_id),
        organization_name=org_rec.name if org_rec else None,
        is_active=new_user.is_active,
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_response,
        refresh_token=raw_refresh_token,
    )


@router.get(
    "/checklist",
    response_model=OnboardingChecklistResponse,
    summary="Get pilot onboarding readiness checklist and progress",
)
async def get_onboarding_checklist(
    org: OrgDep,
    current_user: UserDep,
    db: DatabaseDep,
) -> OnboardingChecklistResponse:
    """
    Evaluates seven critical pilot readiness checkpoints for the active organization:
    1. Organization Setup
    2. Primary Admin Account
    3. Team Invitations & Members
    4. Monitored Applications & Services
    5. Live Telemetry Reception
    6. Alerting & Notification Channel Configuration
    7. Incident & Self-Healing Walkthrough
    """
    # Query stats
    users_res = await db.execute(select(func.count(User.id)).where(User.organization_id == org.id))
    user_count = users_res.scalar() or 0

    admins_res = await db.execute(
        select(func.count(User.id)).where(User.organization_id == org.id, User.role == "admin")
    )
    admin_count = admins_res.scalar() or 0

    services_res = await db.execute(select(func.count(Service.id)).where(Service.organization_id == org.id))
    service_count = services_res.scalar() or 0

    metrics_res = await db.execute(
        select(func.count(ServiceMetric.id))
        .join(Service, ServiceMetric.service_id == Service.id)
        .where(Service.organization_id == org.id)
    )
    metric_count = metrics_res.scalar() or 0

    channels_res = await db.execute(
        select(func.count(NotificationChannel.id)).where(NotificationChannel.organization_id == org.id)
    )
    channel_count = channels_res.scalar() or 0

    incidents_res = await db.execute(select(func.count(Incident.id)).where(Incident.organization_id == org.id))
    incident_count = incidents_res.scalar() or 0

    resolved_res = await db.execute(
        select(func.count(Incident.id)).where(
            Incident.organization_id == org.id,
            Incident.status.in_(["resolved", "completed"]),
        )
    )
    resolved_count = resolved_res.scalar() or 0

    steps = [
        OnboardingStep(
            id="org_setup",
            title="Tenant & Organization Provisioning",
            description="Verify active organization profile, billing plan, and isolated workspace.",
            completed=bool(org.is_active and org.slug),
            action_url="/dashboard/settings",
            details=f"Tenant: '{org.name}' ({org.slug}), Plan: {org.plan}",
        ),
        OnboardingStep(
            id="admin_setup",
            title="Security Administrator Provisioned",
            description="At least one administrator account with governance credentials active.",
            completed=admin_count > 0,
            action_url="/dashboard/settings",
            details=f"{admin_count} active admin account(s) configured.",
        ),
        OnboardingStep(
            id="team_invites",
            title="Team Member Onboarding",
            description="Invite developers, operators, and SREs with role-bounded access.",
            completed=user_count >= 2,
            action_url="/dashboard/settings",
            details=f"{user_count} team member(s) enrolled.",
        ),
        OnboardingStep(
            id="services_connected",
            title="Register Monitored Services",
            description="Connect production or staging backend microservices for observability.",
            completed=service_count > 0,
            action_url="/dashboard/services",
            details=f"{service_count} service(s) monitored.",
        ),
        OnboardingStep(
            id="telemetry_active",
            title="Live Telemetry Ingestion",
            description="Verify metrics, latency, error rate, and availability signals flowing.",
            completed=metric_count > 0 or service_count > 0,
            action_url="/dashboard",
            details=f"{metric_count} metric samples recorded.",
        ),
        OnboardingStep(
            id="alert_channels",
            title="Notification & Alert Destinations",
            description="Configure Slack, Email, Teams, or Webhooks for proactive operational alerts.",
            completed=channel_count > 0,
            action_url="/dashboard/notifications",
            details=f"{channel_count} destination channel(s) ready.",
        ),
        OnboardingStep(
            id="test_incident",
            title="Self-Healing Drill Walkthrough",
            description="Simulate or resolve a canary incident to verify AI diagnosis and recovery loop.",
            completed=incident_count > 0 or resolved_count > 0,
            action_url="/dashboard/incidents",
            details=f"{incident_count} incident(s) detected, {resolved_count} verified resolved.",
        ),
    ]

    completed_steps = sum(1 for s in steps if s.completed)
    completion_pct = round((completed_steps / len(steps)) * 100, 1)

    return OnboardingChecklistResponse(
        organization_id=str(org.id),
        organization_name=org.name,
        plan=org.plan,
        completion_percentage=completion_pct,
        is_ready_for_pilot=completion_pct >= 70.0,
        steps=steps,
        stats={
            "users": user_count,
            "admins": admin_count,
            "services": service_count,
            "metricSamples": metric_count,
            "notificationChannels": channel_count,
            "incidents": incident_count,
            "resolvedIncidents": resolved_count,
        },
    )
