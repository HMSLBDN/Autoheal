"""
AutoHeal DevOps — Phase 10 Pydantic Schemas
Enterprise SSO, User Sessions, Security Audit Logs, and Agent mTLS Certificates.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, EmailStr, ConfigDict


# ==========================================
# 1. Identity Provider Schemas
# ==========================================

class IdentityProviderBase(BaseModel):
    name: str = Field(..., max_length=128)
    idp_type: str = Field("oidc", max_length=32)
    issuer_url: str = Field(..., max_length=512)
    client_id: str = Field(..., max_length=256)
    metadata_url: Optional[str] = Field(None, max_length=512)
    jwks_url: Optional[str] = Field(None, max_length=512)
    authorization_endpoint: Optional[str] = Field(None, max_length=512)
    token_endpoint: Optional[str] = Field(None, max_length=512)
    userinfo_endpoint: Optional[str] = Field(None, max_length=512)
    role_mapping_json: Dict[str, Any] = Field(default_factory=dict)
    allowed_domains: List[str] = Field(default_factory=list)
    is_active: bool = True
    is_enforced: bool = False


class IdentityProviderCreate(IdentityProviderBase):
    client_secret: str = Field(..., min_length=1, description="Raw client secret to be encrypted at rest")


class IdentityProviderUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    client_secret: Optional[str] = None
    metadata_url: Optional[str] = None
    jwks_url: Optional[str] = None
    authorization_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    userinfo_endpoint: Optional[str] = None
    role_mapping_json: Optional[Dict[str, Any]] = None
    allowed_domains: Optional[List[str]] = None
    is_active: Optional[bool] = None
    is_enforced: Optional[bool] = None


class IdentityProviderResponse(IdentityProviderBase):
    id: UUID
    organization_id: UUID
    client_secret_masked: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SsoAuthorizeRequest(BaseModel):
    provider_id: UUID
    redirect_uri: str
    state: Optional[str] = None


class SsoAuthorizeResponse(BaseModel):
    authorization_url: str
    state: str
    code_verifier: str


class SsoCallbackRequest(BaseModel):
    provider_id: UUID
    code: str
    state: str
    code_verifier: str
    redirect_uri: str


class SsoCallbackResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: UUID
    email: str
    role: str
    organization_id: UUID
    session_id: UUID


# ==========================================
# 2. Session Management Schemas
# ==========================================

class UserSessionResponse(BaseModel):
    id: UUID
    user_id: UUID
    organization_id: UUID
    family_id: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_name: Optional[str] = None
    is_active: bool
    expires_at: datetime
    created_at: datetime
    revoked_at: Optional[datetime] = None
    revocation_reason: Optional[str] = None
    is_current: bool = False

    model_config = ConfigDict(from_attributes=True)


class RevokeSessionRequest(BaseModel):
    reason: Optional[str] = Field("User initiated session termination", max_length=256)


# ==========================================
# 3. Security Audit Event Schemas
# ==========================================

class SecurityAuditEventResponse(BaseModel):
    id: UUID
    organization_id: UUID
    user_id: Optional[UUID] = None
    event_type: str
    severity: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details_json: Dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SecurityAuditSummary(BaseModel):
    total_events: int
    critical_events: int
    warning_events: int
    recent_suspicious_activities: List[SecurityAuditEventResponse]


# ==========================================
# 4. Agent mTLS Certificate Schemas
# ==========================================

class AgentCertIssueRequest(BaseModel):
    agent_id: str = Field(..., max_length=64)
    valid_days: int = Field(365, ge=1, le=1825)
    common_name: Optional[str] = None


class AgentCertResponse(BaseModel):
    id: UUID
    organization_id: UUID
    agent_id: str
    serial_number: str
    fingerprint_sha256: str
    subject_dn: str
    issuer_dn: str
    valid_from: datetime
    valid_to: datetime
    is_revoked: bool
    revoked_at: Optional[datetime] = None
    revocation_reason: Optional[str] = None
    cert_pem: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentCertBundleResponse(AgentCertResponse):
    private_key_pem: Optional[str] = None
    ca_cert_pem: str


class AgentCertRevokeRequest(BaseModel):
    reason: str = Field("Manual operator revocation", max_length=256)
