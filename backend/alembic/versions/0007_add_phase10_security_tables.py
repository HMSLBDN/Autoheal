"""Add Phase 10 enterprise security, SSO, user sessions, audit events, and agent mTLS certificates

Revision ID: 0007_add_phase10_security_tables
Revises: 0006_add_phase9_enterprise_tables
Create Date: 2026-11-21 16:45:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0007_add_phase10_security_tables"
down_revision: Union[str, None] = "0006_add_phase9_enterprise_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. identity_provider_configs
    op.create_table(
        "identity_provider_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("idp_type", sa.String(length=32), server_default="oidc", nullable=False),
        sa.Column("issuer_url", sa.String(length=512), nullable=False),
        sa.Column("client_id", sa.String(length=256), nullable=False),
        sa.Column("client_secret_encrypted", sa.Text(), nullable=False),
        sa.Column("metadata_url", sa.String(length=512), nullable=True),
        sa.Column("jwks_url", sa.String(length=512), nullable=True),
        sa.Column("authorization_endpoint", sa.String(length=512), nullable=True),
        sa.Column("token_endpoint", sa.String(length=512), nullable=True),
        sa.Column("userinfo_endpoint", sa.String(length=512), nullable=True),
        sa.Column("role_mapping_json", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("allowed_domains", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_enforced", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_identity_provider_configs_id", "identity_provider_configs", ["id"])
    op.create_index("ix_identity_provider_configs_org", "identity_provider_configs", ["organization_id"])
    op.create_index("ix_idp_org_active", "identity_provider_configs", ["organization_id", "is_active"])

    # 2. user_identity_mappings
    op.create_table(
        "user_identity_mappings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("external_subject_id", sa.String(length=256), nullable=False),
        sa.Column("email", sa.String(length=256), nullable=False),
        sa.Column("raw_claims", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["identity_provider_configs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "external_subject_id", name="uq_provider_external_subject"),
    )
    op.create_index("ix_user_identity_mappings_id", "user_identity_mappings", ["id"])
    op.create_index("ix_user_identity_mappings_org", "user_identity_mappings", ["organization_id"])
    op.create_index("ix_user_identity_org_user", "user_identity_mappings", ["organization_id", "user_id"])

    # 3. user_sessions
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=64), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("device_name", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_sessions_id", "user_sessions", ["id"])
    op.create_index("ix_user_sessions_org", "user_sessions", ["organization_id"])
    op.create_index("ix_user_sessions_token_hash", "user_sessions", ["session_token_hash"], unique=True)
    op.create_index("ix_user_sessions_family", "user_sessions", ["family_id"])
    op.create_index("ix_user_sessions_lookup", "user_sessions", ["user_id", "is_active", "expires_at"])
    op.create_index("ix_user_sessions_org_user", "user_sessions", ["organization_id", "user_id"])

    # 4. security_audit_events
    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), server_default="INFO", nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("details_json", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_audit_events_id", "security_audit_events", ["id"])
    op.create_index("ix_sec_audit_org_event", "security_audit_events", ["organization_id", "event_type", "created_at"])
    op.create_index("ix_sec_audit_severity", "security_audit_events", ["organization_id", "severity", "created_at"])

    # 5. agent_certificates
    op.create_table(
        "agent_certificates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("serial_number", sa.String(length=64), nullable=False),
        sa.Column("fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("subject_dn", sa.String(length=256), nullable=False),
        sa.Column("issuer_dn", sa.String(length=256), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=256), nullable=True),
        sa.Column("cert_pem", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["infrastructure_agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("serial_number", name="uq_agent_cert_serial"),
        sa.UniqueConstraint("fingerprint_sha256", name="uq_agent_cert_fingerprint"),
    )
    op.create_index("ix_agent_certificates_id", "agent_certificates", ["id"])
    op.create_index("ix_agent_cert_lookup", "agent_certificates", ["organization_id", "agent_id", "is_revoked"])
    op.create_index("ix_agent_cert_valid_to", "agent_certificates", ["valid_to"])


def downgrade() -> None:
    op.drop_table("agent_certificates")
    op.drop_table("security_audit_events")
    op.drop_table("user_sessions")
    op.drop_table("user_identity_mappings")
    op.drop_table("identity_provider_configs")
