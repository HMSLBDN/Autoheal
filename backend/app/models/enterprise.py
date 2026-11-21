"""
AutoHeal DevOps — Enterprise Integrations, Notifications, Incident Collaboration,
Escalations, and Canary Release Evaluation Models
Multi-tenant, audited, and strictly scoped by organization_id.
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
import uuid
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, utc_now

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.service import Service
    from app.models.incident import Incident
    from app.models.user import User


class NotificationChannel(Base, TimestampMixin):
    """
    Configured notification destination adapter (Slack, MS Teams, Email, Generic Webhook).
    Disabled by default until explicitly enabled by an organization admin.
    """
    __tablename__ = "notification_channels"
    __table_args__ = (
        Index("ix_channels_org_type", "organization_id", "channel_type"),
        Index("ix_channels_org_enabled", "organization_id", "is_enabled"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )  # e.g. "Primary SRE Slack Channel", "PagerDuty High-Sev"
    channel_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # email, slack, teams, webhook
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )  # Mandatory: Disabled by default
    config_json: Mapped[str] = mapped_column(
        Text,
        default="{}",
        nullable=False,
    )  # Target URL, recipient emails, or team channel ID (secrets masked)
    secret_token: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )  # Server-side auth token or signing key, never exposed to client
    rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer,
        default=30,
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    subscriptions: Mapped[List["NotificationSubscription"]] = relationship(
        "NotificationSubscription",
        back_populates="channel",
        cascade="all, delete-orphan",
    )
    deliveries: Mapped[List["NotificationDelivery"]] = relationship(
        "NotificationDelivery",
        back_populates="channel",
        cascade="all, delete-orphan",
    )


class NotificationSubscription(Base):
    """
    Event subscription linking specific incident/recovery lifecycle triggers to a channel.
    """
    __tablename__ = "notification_subscriptions"
    __table_args__ = (
        Index("ix_sub_org_channel", "organization_id", "channel_id"),
        Index("ix_sub_org_event", "organization_id", "event_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("notification_channels.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )  # incident_created_critical, recovery_completed, etc.
    min_severity: Mapped[str] = mapped_column(
        String(50),
        default="medium",
        nullable=False,
    )  # informational, low, medium, high, critical
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    channel: Mapped["NotificationChannel"] = relationship("NotificationChannel", back_populates="subscriptions")


class NotificationDelivery(Base):
    """
    Delivery history log tracking dispatch, retries, exponential backoff, and delivery status.
    """
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        Index("ix_deliveries_org_status", "organization_id", "status"),
        Index("ix_deliveries_org_idempotency", "organization_id", "idempotency_key", unique=True),
        Index("ix_deliveries_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("notification_channels.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    incident_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("incidents.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )  # Redacted minimal notification payload
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
    )  # pending, processing, delivered, retrying, failed, permanently_failed, disabled
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    max_retries: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
    )
    provider_response_code: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )  # Redacted reason, never logs secret tokens
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    channel: Mapped["NotificationChannel"] = relationship("NotificationChannel", back_populates="deliveries")
    incident: Mapped[Optional["Incident"]] = relationship("Incident")


class WebhookEndpoint(Base, TimestampMixin):
    """
    Generic outbound webhook endpoint configured to receive signed AutoHeal events.
    Enforces SSRF protections and HMAC-SHA256 signatures.
    """
    __tablename__ = "webhook_endpoints"
    __table_args__ = (
        Index("ix_webhooks_org_active", "organization_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    target_url: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )
    secret_token: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )  # HMAC-SHA256 signing secret, server-side only
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )  # Disabled by default
    events_json: Mapped[str] = mapped_column(
        Text,
        default='["*"]',
        nullable=False,
    )  # Subscribed events array
    timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        default=10,
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    delivery_attempts: Mapped[List["WebhookDeliveryAttempt"]] = relationship(
        "WebhookDeliveryAttempt",
        back_populates="endpoint",
        cascade="all, delete-orphan",
    )


class WebhookDeliveryAttempt(Base):
    """
    Audit log of outbound HTTP webhook invocations, recording signature headers and latency.
    """
    __tablename__ = "webhook_delivery_attempts"
    __table_args__ = (
        Index("ix_wh_attempts_org_created", "organization_id", "created_at"),
        Index("ix_wh_attempts_endpoint", "endpoint_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    delivery_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )  # UUID header for replay deduplication
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    signature_header: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    response_status_code: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # success, failed
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    duration_ms: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    endpoint: Mapped["WebhookEndpoint"] = relationship("WebhookEndpoint", back_populates="delivery_attempts")


class IncidentComment(Base):
    """
    Communication timeline entry attached to an incident (comments, internal notes, resolution summaries).
    """
    __tablename__ = "incident_comments"
    __table_args__ = (
        Index("ix_comments_org_inc", "organization_id", "incident_id"),
        Index("ix_comments_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    incident_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    author_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    author_role: Mapped[str] = mapped_column(
        String(50),
        default="operator",
        nullable=False,
    )  # operator, admin, viewer, system
    comment_type: Mapped[str] = mapped_column(
        String(50),
        default="comment",
        nullable=False,
    )  # comment, internal_note, status_change, escalation, resolution_summary
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    incident: Mapped["Incident"] = relationship("Incident")
    user: Mapped[Optional["User"]] = relationship("User")


class IncidentAssignment(Base):
    """
    Ownership assignment log for an incident.
    """
    __tablename__ = "incident_assignments"
    __table_args__ = (
        Index("ix_assign_org_inc", "organization_id", "incident_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    incident_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    assigned_to_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_to_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    assigned_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_by_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    incident: Mapped["Incident"] = relationship("Incident")


class EscalationPolicy(Base, TimestampMixin):
    """
    Configurable escalation rules for unacknowledged incidents and severity thresholds.
    """
    __tablename__ = "escalation_policies"
    __table_args__ = (
        Index("ix_esc_org_active", "organization_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )  # e.g. "Critical Service Tier-1 Escalation"
    severity: Mapped[str] = mapped_column(
        String(50),
        default="critical",
        nullable=False,
    )  # critical, high
    unacknowledged_timeout_minutes: Mapped[int] = mapped_column(
        Integer,
        default=15,
        nullable=False,
    )
    max_escalation_level: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
    )
    rules_json: Mapped[str] = mapped_column(
        Text,
        default="[]",
        nullable=False,
    )  # Structured level rules with channel IDs and roles
    quiet_hours_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    quiet_hours_start_utc: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
    )  # "22:00"
    quiet_hours_end_utc: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
    )  # "06:00"
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    escalation_events: Mapped[List["EscalationEvent"]] = relationship(
        "EscalationEvent",
        back_populates="policy",
        cascade="all, delete-orphan",
    )


class EscalationEvent(Base):
    """
    Historical record of an escalation level triggered for an incident.
    """
    __tablename__ = "escalation_events"
    __table_args__ = (
        Index("ix_esc_event_org_inc", "organization_id", "incident_id"),
        Index("ix_esc_event_time", "escalated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("escalation_policies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    incident_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    escalation_level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    trigger_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    action_taken: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    notified_channels_json: Mapped[str] = mapped_column(
        Text,
        default="[]",
        nullable=False,
    )
    escalated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    policy: Mapped["EscalationPolicy"] = relationship("EscalationPolicy", back_populates="escalation_events")
    incident: Mapped["Incident"] = relationship("Incident")


class ReleaseEvaluation(Base):
    """
    Canary and progressive rollout evaluation record. Strictly advisory / simulated.
    """
    __tablename__ = "release_evaluations"
    __table_args__ = (
        Index("ix_release_eval_org_svc", "organization_id", "service_id"),
        Index("ix_release_eval_time", "evaluated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    service_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("services.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    release_tag: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )  # e.g. "v2.5.0-rc1"
    stage: Mapped[str] = mapped_column(
        String(50),
        default="canary",
        nullable=False,
    )  # baseline, canary, progressive_rollout, final_evaluation, completed, paused, rejected, rollback_recommended
    status: Mapped[str] = mapped_column(
        String(50),
        default="passed",
        nullable=False,
    )  # healthy, degraded, critical, passed, failed
    traffic_percentage: Mapped[int] = mapped_column(
        Integer,
        default=10,
        nullable=False,
    )
    observation_window_minutes: Mapped[int] = mapped_column(
        Integer,
        default=30,
        nullable=False,
    )
    sample_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    baseline_metrics_json: Mapped[str] = mapped_column(
        Text,
        default="{}",
        nullable=False,
    )
    canary_metrics_json: Mapped[str] = mapped_column(
        Text,
        default="{}",
        nullable=False,
    )
    thresholds_json: Mapped[str] = mapped_column(
        Text,
        default="{}",
        nullable=False,
    )
    regression_detected: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    recommendation: Mapped[str] = mapped_column(
        String(100),
        default="proceed",
        nullable=False,
    )  # proceed, pause, rollback_recommended
    explanation: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    service: Mapped["Service"] = relationship("Service")
    metrics: Mapped[List["ReleaseEvaluationMetric"]] = relationship(
        "ReleaseEvaluationMetric",
        back_populates="evaluation",
        cascade="all, delete-orphan",
    )


class ReleaseEvaluationMetric(Base):
    """
    Individual metric evaluation (error rate, latency, CPU, memory) for a canary release.
    """
    __tablename__ = "release_evaluation_metrics"
    __table_args__ = (
        Index("ix_rel_eval_metric_eval", "evaluation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("release_evaluations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    metric_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # error_rate, latency_ms, cpu_percent, memory_percent, availability
    baseline_value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    canary_value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    delta: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    threshold_value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="pass",
        nullable=False,
    )  # pass, warning, breach
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    evaluation: Mapped["ReleaseEvaluation"] = relationship("ReleaseEvaluation", back_populates="metrics")
