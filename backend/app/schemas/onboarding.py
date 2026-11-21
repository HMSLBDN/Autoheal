"""
AutoHeal DevOps — Onboarding & Team Invitation Schemas
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field


class InviteCreateRequest(BaseModel):
    """Request payload to invite a new team member."""
    email: EmailStr = Field(..., description="Target email of the team member")
    role: str = Field(default="operator", description="Role: viewer, operator, admin")


class InviteResponse(BaseModel):
    """Response returned when an invitation is generated or queried."""
    id: str
    email: str
    role: str
    organization_id: str
    invited_by_email: Optional[str] = None
    invitation_token: Optional[str] = None
    invite_url: Optional[str] = None
    expires_at: datetime
    is_accepted: bool
    created_at: datetime


class AcceptInviteRequest(BaseModel):
    """Payload to accept an invitation and activate user account."""
    token: str = Field(..., description="Raw secret invitation token")
    full_name: str = Field(..., min_length=2, max_length=255, description="Full name of user")
    password: str = Field(..., min_length=8, max_length=128, description="Strong password")


class OnboardingStep(BaseModel):
    """Individual verification checkpoint in pilot onboarding."""
    id: str
    title: str
    description: str
    completed: bool
    action_url: str
    details: Optional[str] = None


class OnboardingChecklistResponse(BaseModel):
    """Comprehensive readiness checklist for engineering pilot onboarding."""
    organization_id: str
    organization_name: str
    plan: str
    completion_percentage: float
    is_ready_for_pilot: bool
    steps: List[OnboardingStep]
    stats: Dict[str, Any]
