"""
AutoHeal DevOps — Phase 10 Enterprise Models
Includes Enterprise SSO / Identity Providers, User Identity Mappings,
Active User Sessions, Security Audit Events, and mTLS Agent Certificates.
"""

from datetime import datetime, timezone
import uuid
from typing import Optional, Dict, Any, List

from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    JSON,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, utc_now


class IdentityProviderConfig(Base, TimestampMixin):
    """
    Enterprise SSO Identity Provider configuration (OIDC / SAML 2.0).
    Scoped per organization for strict multi-tenant isolation.
    """
    __tablename__ = "identity_provider_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    idp_type: Mapped[str] = mapped_column(String(32), default="oidc", nullable=False)  # 'oidc', 'saml'
    issuer_url: Mapped[str] = mapped_column(String(512), nullable=False)
    client_id: Mapped[str] = mapped_column(String(256), nullable=False)
    client_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    jwks_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    authorization_endpoint: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    token_endpoint: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    userinfo_endpoint: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    # Role mapping: e.g. {"admin": ["DevOps-Admins", "Platform-Engineers"], "operator": ["SRE-Team"], "viewer": ["Engineers"]}
    role_mapping_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    
    # Allowed domains for JIT provisioning and SSO enforcement: e.g. ["company.com", "enterprise.org"]
    allowed_domains: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_enforced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Disables password login for org domains

    __table_args__ = (
        Index("ix_idp_org_active", "organization_id", "is_active"),
    )


class UserIdentityMapping(Base, TimestampMixin):
    """
    Maps an external IdP subject (sub) claim to an internal AutoHeal User.
    Strictly scoped to organization to prevent cross-tenant identity injection or account takeover.
    """
    __tablename__ = "user_identity_mappings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("identity_provider_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_subject_id: Mapped[str] = mapped_column(String(256), nullable=False)
    email: Mapped[str] = mapped_column(String(256), nullable=False)
    raw_claims: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("provider_id", "external_subject_id", name="uq_provider_external_subject"),
        Index("ix_user_identity_org_user", "organization_id", "user_id"),
    )


class UserSession(Base, TimestampMixin):
    """
    Active multi-device session tracking with instant revocation and device fingerprinting.
    """
    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    family_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    device_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    __table_args__ = (
        Index("ix_user_sessions_lookup", "user_id", "is_active", "expires_at"),
        Index("ix_user_sessions_org", "organization_id", "user_id"),
    )


class SecurityAuditEvent(Base, TimestampMixin):
    """
    Dedicated audit logging for high-security enterprise actions:
    failed logins, token replay detection, cert rotations, mTLS handshakes,
    session revocations, break-glass recovery bypasses.
    """
    __tablename__ = "security_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), default="INFO", nullable=False)  # 'INFO', 'WARNING', 'CRITICAL'
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    details_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_sec_audit_org_event", "organization_id", "event_type", "created_at"),
        Index("ix_sec_audit_severity", "organization_id", "severity", "created_at"),
    )


class AgentCertificate(Base, TimestampMixin):
    """
    X.509 client certificate issued to an Infrastructure Agent for mutual TLS (mTLS).
    Contains fingerprint, Subject DN, validity period, and revocation lifecycle tracking.
    """
    __tablename__ = "agent_certificates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("infrastructure_agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    serial_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    fingerprint_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    subject_dn: Mapped[str] = mapped_column(String(256), nullable=False)
    issuer_dn: Mapped[str] = mapped_column(String(256), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    cert_pem: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_agent_cert_lookup", "organization_id", "agent_id", "is_revoked"),
    )
