"""
AutoHeal DevOps — Settings & Workspace Configuration Router
Provides safe read and update access to user, organization, and environment settings.
Strictly redacts all secrets, database credentials, and internal API keys.
"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DatabaseDep, OrgDep, RequireOperatorDep, UserDep
from app.config import get_settings
from app.models.audit import AuditLog
from app.schemas.settings import (
    EnvironmentSettingsResponse,
    OrgSettingsResponse,
    UpdateSettingsRequest,
    UserSettingsResponse,
    WorkspaceSettingsResponse,
)

settings_config = get_settings()

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get(
    "",
    response_model=WorkspaceSettingsResponse,
    summary="Get current user, organization, and platform settings",
)
async def get_settings_view(
    org: OrgDep,
    current_user: UserDep,
) -> WorkspaceSettingsResponse:
    """
    Returns non-sensitive organization, user, and governance settings.
    Guarantees no secret keys, JWT secrets, or DB passwords are leaked.
    """
    return WorkspaceSettingsResponse(
        organization=OrgSettingsResponse(
            id=str(org.id),
            slug=org.slug,
            name=org.name,
            plan=org.plan,
            is_active=org.is_active,
        ),
        user=UserSettingsResponse(
            id=str(current_user.id),
            email=current_user.email,
            full_name=current_user.full_name,
            role=current_user.role,
            is_active=current_user.is_active,
        ),
        environment=EnvironmentSettingsResponse(
            app_env=settings_config.APP_ENV,
            ai_provider=settings_config.AI_PROVIDER,
            monitoring_interval_seconds=settings_config.METRIC_SCRAPE_INTERVAL_SECONDS,
            max_recovery_retries=settings_config.MAX_RECOVERY_RETRIES,
            recovery_cooldown_seconds=settings_config.RECOVERY_COOLDOWN_SECONDS,
        ),
    )


@router.patch(
    "",
    response_model=WorkspaceSettingsResponse,
    summary="Update organization or user settings",
)
async def update_settings(
    payload: UpdateSettingsRequest,
    org: OrgDep,
    current_user: RequireOperatorDep,
    db: DatabaseDep,
) -> WorkspaceSettingsResponse:
    """
    Updates user display name or organization name.
    Requires operator or admin role. Emits audit log entry.
    """
    updated_fields = []
    if payload.full_name:
        current_user.full_name = payload.full_name.strip()
        updated_fields.append(f"user full_name to '{current_user.full_name}'")

    if payload.organization_name:
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can update the organization name.",
            )
        org.name = payload.organization_name.strip()
        updated_fields.append(f"organization name to '{org.name}'")

    if updated_fields:
        db.add(AuditLog(
            organization_id=org.id,
            user_id=current_user.id,
            action="settings_updated",
            resource_type="organization",
            resource_id=str(org.id),
            details=f"User '{current_user.email}' updated {', '.join(updated_fields)}.",
        ))
        await db.commit()
        await db.refresh(current_user)
        await db.refresh(org)

    return await get_settings_view(org=org, current_user=current_user)
