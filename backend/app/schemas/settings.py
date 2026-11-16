"""
AutoHeal DevOps — Settings Schemas
"""

from typing import Optional
from pydantic import BaseModel, Field


class UserSettingsResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool


class OrgSettingsResponse(BaseModel):
    id: str
    slug: str
    name: str
    plan: str
    is_active: bool


class EnvironmentSettingsResponse(BaseModel):
    app_env: str
    ai_provider: str
    monitoring_interval_seconds: int
    max_recovery_retries: int
    recovery_cooldown_seconds: int


class WorkspaceSettingsResponse(BaseModel):
    organization: OrgSettingsResponse
    user: UserSettingsResponse
    environment: EnvironmentSettingsResponse


class UpdateSettingsRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    organization_name: Optional[str] = Field(None, min_length=2, max_length=100)
