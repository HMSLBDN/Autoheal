"""Initial database schema: 15 core AutoHeal tables

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-11-16 19:55:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. organizations
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("plan", sa.String(length=50), nullable=False, server_default="starter"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    # 2. users
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="operator"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_organization_id", "users", ["organization_id"], unique=False)

    # 3. refresh_tokens
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"], unique=False)
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False)
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"], unique=False)

    # 4. services
    op.create_table(
        "services",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("environment", sa.String(length=50), nullable=False, server_default="production"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="healthy"),
        sa.Column("availability", sa.Float(), nullable=False, server_default="99.9"),
        sa.Column("error_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("last_checked", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_services_organization_id", "services", ["organization_id"], unique=False)
    op.create_index("ix_services_name", "services", ["name"], unique=False)
    op.create_index("ix_services_environment", "services", ["environment"], unique=False)
    op.create_index("ix_services_status", "services", ["status"], unique=False)

    # 5. service_monitors
    op.create_table(
        "service_monitors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.String(length=100), nullable=False),
        sa.Column("metrics_path", sa.String(length=255), nullable=False, server_default="/metrics"),
        sa.Column("health_check_path", sa.String(length=255), nullable=False, server_default="/healthz"),
        sa.Column("scrape_interval_seconds", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_monitors_service_id", "service_monitors", ["service_id"], unique=False)

    # 6. alert_configs
    op.create_table(
        "alert_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.String(length=100), nullable=False),
        sa.Column("metric_name", sa.String(length=100), nullable=False),
        sa.Column("condition", sa.String(length=20), nullable=False, server_default="gt"),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("severity", sa.String(length=50), nullable=False, server_default="high"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_configs_service_id", "alert_configs", ["service_id"], unique=False)

    # 7. deployment_events
    op.create_table(
        "deployment_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.String(length=100), nullable=False),
        sa.Column("release_tag", sa.String(length=100), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("deployed_by", sa.String(length=100), nullable=False, server_default="CI/CD Pipeline"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="success"),
        sa.Column("manifest_summary", sa.Text(), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deployment_events_service_id", "deployment_events", ["service_id"], unique=False)
    op.create_index("ix_deployment_events_deployed_at", "deployment_events", ["deployed_at"], unique=False)

    # 8. recovery_policies
    op.create_table(
        "recovery_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="900"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("auto_approve_threshold", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recovery_policies_service_id", "recovery_policies", ["service_id"], unique=False)

    # 9. incidents
    op.create_table(
        "incidents",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.String(length=100), nullable=False),
        sa.Column("service_name", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("severity", sa.String(length=50), nullable=False, server_default="high"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="open"),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recovery_status", sa.String(length=100), nullable=False, server_default="Not started"),
        sa.Column("error_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("threshold", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("probable_cause", sa.Text(), nullable=False, server_default=""),
        sa.Column("recommended_action", sa.Text(), nullable=False, server_default=""),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incidents_organization_id", "incidents", ["organization_id"], unique=False)
    op.create_index("ix_incidents_service_id", "incidents", ["service_id"], unique=False)
    op.create_index("ix_incidents_status", "incidents", ["status"], unique=False)
    op.create_index("ix_incidents_severity", "incidents", ["severity"], unique=False)
    op.create_index("ix_incidents_detected_at", "incidents", ["detected_at"], unique=False)

    # 10. incident_evidence
    op.create_table(
        "incident_evidence",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("incident_id", sa.String(length=50), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incident_evidence_incident_id", "incident_evidence", ["incident_id"], unique=False)

    # 11. incident_events
    op.create_table(
        "incident_events",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("incident_id", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tone", sa.String(length=50), nullable=False, server_default="neutral"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incident_events_incident_id", "incident_events", ["incident_id"], unique=False)

    # 12. recovery_actions
    op.create_table(
        "recovery_actions",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("incident_id", sa.String(length=50), nullable=False),
        sa.Column("service_id", sa.String(length=100), nullable=False),
        sa.Column("service_name", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending_approval"),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("requested_by", sa.String(length=100), nullable=False, server_default="AutoHeal policy"),
        sa.Column("approver_id", sa.Uuid(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("verification", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approver_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recovery_actions_incident_id", "recovery_actions", ["incident_id"], unique=False)
    op.create_index("ix_recovery_actions_service_id", "recovery_actions", ["service_id"], unique=False)
    op.create_index("ix_recovery_actions_status", "recovery_actions", ["status"], unique=False)
    op.create_index("ix_recovery_actions_requested_at", "recovery_actions", ["requested_at"], unique=False)

    # 13. recovery_results
    op.create_table(
        "recovery_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recovery_action_id", sa.String(length=50), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("diagnostic_output", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["recovery_action_id"], ["recovery_actions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recovery_results_recovery_action_id", "recovery_results", ["recovery_action_id"], unique=True)

    # 14. service_metrics
    op.create_table(
        "service_metrics",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("service_id", sa.String(length=100), nullable=False),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cpu_percent", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("memory_percent", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("request_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("error_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("availability", sa.Float(), nullable=False, server_default="100.0"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_metrics_service_id", "service_metrics", ["service_id"], unique=False)
    op.create_index("ix_service_metrics_sampled_at", "service_metrics", ["sampled_at"], unique=False)

    # 15. audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.String(length=100), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"], unique=False)
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"], unique=False)
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)


def downgrade() -> None:
    # Drop in reverse topological order
    op.drop_table("audit_logs")
    op.drop_table("service_metrics")
    op.drop_table("recovery_results")
    op.drop_table("recovery_actions")
    op.drop_table("incident_events")
    op.drop_table("incident_evidence")
    op.drop_table("incidents")
    op.drop_table("recovery_policies")
    op.drop_table("deployment_events")
    op.drop_table("alert_configs")
    op.drop_table("service_monitors")
    op.drop_table("services")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    op.drop_table("organizations")
