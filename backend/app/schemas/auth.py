"""
AutoHeal DevOps — Authentication & User Schemas
"""

from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegisterRequest(BaseModel):
    """Payload for self-service user registration."""
    email: EmailStr = Field(..., description="User's unique email address")
    password: str = Field(..., min_length=8, max_length=128, description="Password (at least 8 characters)")
    full_name: str = Field(..., min_length=2, max_length=255, description="Full name or display name")
    role: Optional[str] = Field("operator", description="Requested role (default: operator; admin cannot be self-assigned)")


class UserLoginRequest(BaseModel):
    """Payload for user authentication."""
    email: EmailStr = Field(..., description="Registered work email")
    password: str = Field(..., min_length=1, description="Account password")


class UserResponse(BaseModel):
    """Authenticated user profile representation."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: str
    organization_id: str
    organization_name: Optional[str] = None
    is_active: bool = True


class TokenResponse(BaseModel):
    """JWT access token and authentication profile response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # 15 minutes
    user: UserResponse
    refresh_token: Optional[str] = Field(None, description="Returned for programmatic / non-browser clients")


class TokenRefreshRequest(BaseModel):
    """Refresh token payload when cookies are not utilized."""
    refresh_token: Optional[str] = Field(None, description="Refresh token from client storage")


class ForgotPasswordRequest(BaseModel):
    """Initiates self-service password recovery."""
    email: EmailStr = Field(..., description="Email address to receive recovery instructions")


class ResetPasswordRequest(BaseModel):
    """Completes password reset using verified token."""
    token: str = Field(..., min_length=10, description="One-time password reset token")
    new_password: str = Field(..., min_length=8, max_length=128, description="New account password (min 8 characters)")


class AuthMessageResponse(BaseModel):
    """Generic status response for auth operations (logout, password reset)."""
    message: str
    status: str = "success"
