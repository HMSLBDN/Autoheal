"""Add Phase 9 enterprise notifications, webhooks, incident collaboration, escalations, and canary release tables

Revision ID: 0006_add_phase9_enterprise_tables
Revises: 0005_add_phase8_intelligence_tables
Create Date: 2026-11-21 16:10:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006_add_phase9_enterprise_tables"
down_revision: Union[str, None] = "0005_add_phase8_intelligence_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. notification_channels
    op.create_table(
        "notification_channels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("channel_type", sa.String(length=50), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("config_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("secret_token", sa.String(length=255), nullable=True),
        sa.Column("rate_limit_per_minute", sa.Integer(), server_default="30", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_channels_id", "notification_channels", ["id"])
    op.create_index("ix_notification_channels_org", "notification_channels", ["organization_id"])
    op.create_index("ix_channels_org_type", "notification_channels", ["organization_id", "channel_type"])
    op.create_index("ix_channels_org_enabled", "notification_channels", ["organization_id", "is_enabled"])

    # 2. notification_subscriptions
    op.create_table(
        "notification_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("min_severity", sa.String(length=50), server_default="medium", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], ["notification_channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_subscriptions_id", "notification_subscriptions", ["id"])
    op.create_index("ix_notification_subscriptions_org", "notification_subscriptions", ["organization_id"])
    op.create_index("ix_sub_org_channel", "notification_subscriptions", ["organization_id", "channel_id"])
    op.create_index("ix_sub_org_event", "notification_subscriptions", ["organization_id", "event_type"])

    # 3. notification_deliveries
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("channel_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.String(length=50), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=150), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_retries", sa.Integer(), server_default="3", nullable=False),
        sa.Column("provider_response_code", sa.Integer(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], ["notification_channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_deliveries_id", "notification_deliveries", ["id"])
    op.create_index("ix_notification_deliveries_org", "notification_deliveries", ["organization_id"])
    op.create_index("ix_deliveries_org_status", "notification_deliveries", ["organization_id", "status"])
    op.create_index("ix_deliveries_org_idempotency", "notification_deliveries", ["organization_id", "idempotency_key"], unique=True)
    op.create_index("ix_deliveries_created_at", "notification_deliveries", ["created_at"])

    # 4. webhook_endpoints
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("target_url", sa.String(length=1000), nullable=False),
        sa.Column("secret_token", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("events_json", sa.Text(), server_default='["*"]', nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), server_default="10", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_endpoints_id", "webhook_endpoints", ["id"])
    op.create_index("ix_webhook_endpoints_org", "webhook_endpoints", ["organization_id"])
    op.create_index("ix_webhooks_org_active", "webhook_endpoints", ["organization_id", "is_active"])

    # 5. webhook_delivery_attempts
    op.create_table(
        "webhook_delivery_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_id", sa.Uuid(), nullable=False),
        sa.Column("delivery_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("signature_header", sa.String(length=255), nullable=False),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["endpoint_id"], ["webhook_endpoints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_delivery_attempts_id", "webhook_delivery_attempts", ["id"])
    op.create_index("ix_webhook_delivery_attempts_org", "webhook_delivery_attempts", ["organization_id"])
    op.create_index("ix_wh_attempts_org_created", "webhook_delivery_attempts", ["organization_id", "created_at"])
    op.create_index("ix_wh_attempts_endpoint", "webhook_delivery_attempts", ["endpoint_id"])

    # 6. incident_comments
    op.create_table(
        "incident_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.String(length=50), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("author_name", sa.String(length=150), nullable=False),
        sa.Column("author_role", sa.String(length=50), server_default="operator", nullable=False),
        sa.Column("comment_type", sa.String(length=50), server_default="comment", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incident_comments_id", "incident_comments", ["id"])
    op.create_index("ix_incident_comments_org", "incident_comments", ["organization_id"])
    op.create_index("ix_comments_org_inc", "incident_comments", ["organization_id", "incident_id"])
    op.create_index("ix_comments_created", "incident_comments", ["created_at"])

    # 7. incident_assignments
    op.create_table(
        "incident_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.String(length=50), nullable=False),
        sa.Column("assigned_to_user_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_to_name", sa.String(length=150), nullable=False),
        sa.Column("assigned_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_by_name", sa.String(length=150), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incident_assignments_id", "incident_assignments", ["id"])
    op.create_index("ix_incident_assignments_org", "incident_assignments", ["organization_id"])
    op.create_index("ix_assign_org_inc", "incident_assignments", ["organization_id", "incident_id"])

    # 8. escalation_policies
    op.create_table(
        "escalation_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("severity", sa.String(length=50), server_default="critical", nullable=False),
        sa.Column("unacknowledged_timeout_minutes", sa.Integer(), server_default="15", nullable=False),
        sa.Column("max_escalation_level", sa.Integer(), server_default="3", nullable=False),
        sa.Column("rules_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column("quiet_hours_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("quiet_hours_start_utc", sa.String(length=10), nullable=True),
        sa.Column("quiet_hours_end_utc", sa.String(length=10), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_escalation_policies_id", "escalation_policies", ["id"])
    op.create_index("ix_escalation_policies_org", "escalation_policies", ["organization_id"])
    op.create_index("ix_esc_org_active", "escalation_policies", ["organization_id", "is_active"])

    # 9. escalation_events
    op.create_table(
        "escalation_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("policy_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.String(length=50), nullable=False),
        sa.Column("escalation_level", sa.Integer(), nullable=False),
        sa.Column("trigger_reason", sa.Text(), nullable=False),
        sa.Column("action_taken", sa.Text(), nullable=False),
        sa.Column("notified_channels_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["escalation_policies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_escalation_events_id", "escalation_events", ["id"])
    op.create_index("ix_escalation_events_org", "escalation_events", ["organization_id"])
    op.create_index("ix_esc_event_org_inc", "escalation_events", ["organization_id", "incident_id"])
    op.create_index("ix_esc_event_time", "escalation_events", ["escalated_at"])

    # 10. release_evaluations
    op.create_table(
        "release_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.String(length=100), nullable=False),
        sa.Column("release_tag", sa.String(length=100), nullable=False),
        sa.Column("stage", sa.String(length=50), server_default="canary", nullable=False),
        sa.Column("status", sa.String(length=50), server_default="passed", nullable=False),
        sa.Column("traffic_percentage", sa.Integer(), server_default="10", nullable=False),
        sa.Column("observation_window_minutes", sa.Integer(), server_default="30", nullable=False),
        sa.Column("sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("baseline_metrics_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("canary_metrics_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("thresholds_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("regression_detected", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("recommendation", sa.String(length=100), server_default="proceed", nullable=False),
        sa.Column("explanation", sa.Text(), server_default="", nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_release_evaluations_id", "release_evaluations", ["id"])
    op.create_index("ix_release_evaluations_org", "release_evaluations", ["organization_id"])
    op.create_index("ix_release_eval_org_svc", "release_evaluations", ["organization_id", "service_id"])
    op.create_index("ix_release_eval_time", "release_evaluations", ["evaluated_at"])

    # 11. release_evaluation_metrics
    op.create_table(
        "release_evaluation_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("metric_name", sa.String(length=50), nullable=False),
        sa.Column("baseline_value", sa.Float(), nullable=False),
        sa.Column("canary_value", sa.Float(), nullable=False),
        sa.Column("delta", sa.Float(), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="pass", nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_id"], ["release_evaluations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_release_evaluation_metrics_id", "release_evaluation_metrics", ["id"])
    op.create_index("ix_rel_eval_metric_eval", "release_evaluation_metrics", ["evaluation_id"])


def downgrade() -> None:
    op.drop_table("release_evaluation_metrics")
    op.drop_table("release_evaluations")
    op.drop_table("escalation_events")
    op.drop_table("escalation_policies")
    op.drop_table("incident_assignments")
    op.drop_table("incident_comments")
    op.drop_table("webhook_delivery_attempts")
    op.drop_table("webhook_endpoints")
    op.drop_table("notification_deliveries")
    op.drop_table("notification_subscriptions")
    op.drop_table("notification_channels")
