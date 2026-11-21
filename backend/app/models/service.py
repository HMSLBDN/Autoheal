"""
AutoHeal DevOps — Service & Infrastructure Configuration Models
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
import uuid
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, utc_now

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.incident import Incident
    from app.models.recovery import RecoveryAction
    from app.models.metric import ServiceMetric


class Service(Base, TimestampMixin):
    """
    Monitored infrastructure service entity.
    Directly satisfies the frontend Service contract in types/index.ts.
    """
    __tablename__ = "services"
    __table_args__ = (
        Index("ix_services_org_env", "organization_id", "environment"),
    )

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )  # e.g. "svc-api", "svc-web", or UUID
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )
    environment: Mapped[str] = mapped_column(
        String(50),
        default="production",
        index=True,
        nullable=False,
    )  # production, staging
    status: Mapped[str] = mapped_column(
        String(50),
        default="healthy",
        index=True,
        nullable=False,
    )  # healthy, degraded, critical
    availability: Mapped[float] = mapped_column(
        Float,
        default=99.9,
        nullable=False,
    )
    error_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    latency_ms: Mapped[int] = mapped_column(
        Integer,
        default=100,
        nullable=False,
    )
    last_checked: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="services",
    )
    monitors: Mapped[List["ServiceMonitor"]] = relationship(
        "ServiceMonitor",
        back_populates="service",
        cascade="all, delete-orphan",
    )
    alert_configs: Mapped[List["AlertConfig"]] = relationship(
        "AlertConfig",
        back_populates="service",
        cascade="all, delete-orphan",
    )
    deployment_events: Mapped[List["DeploymentEvent"]] = relationship(
        "DeploymentEvent",
        back_populates="service",
        cascade="all, delete-orphan",
    )
    recovery_policies: Mapped[List["RecoveryPolicy"]] = relationship(
        "RecoveryPolicy",
        back_populates="service",
        cascade="all, delete-orphan",
    )
    incidents: Mapped[List["Incident"]] = relationship(
        "Incident",
        back_populates="service",
        cascade="all, delete-orphan",
    )
    recovery_actions: Mapped[List["RecoveryAction"]] = relationship(
        "RecoveryAction",
        back_populates="service",
        cascade="all, delete-orphan",
    )
    metrics: Mapped[List["ServiceMetric"]] = relationship(
        "ServiceMetric",
        back_populates="service",
        cascade="all, delete-orphan",
    )


class ServiceMonitor(Base, TimestampMixin):
    """
    Monitoring configuration for scraping and probing service telemetry.
    """
    __tablename__ = "service_monitors"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    service_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("services.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    metrics_path: Mapped[str] = mapped_column(
        String(255),
        default="/metrics",
        nullable=False,
    )
    health_check_path: Mapped[str] = mapped_column(
        String(255),
        default="/healthz",
        nullable=False,
    )
    scrape_interval_seconds: Mapped[int] = mapped_column(
        Integer,
        default=15,
        nullable=False,
    )
    timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    service: Mapped["Service"] = relationship(
        "Service",
        back_populates="monitors",
    )


class AlertConfig(Base, TimestampMixin):
    """
    Configured metric alerting rules and thresholds per service.
    """
    __tablename__ = "alert_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    service_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("services.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    metric_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )  # error_rate, latency_ms, cpu_percent
    condition: Mapped[str] = mapped_column(
        String(20),
        default="gt",
        nullable=False,
    )  # gt, lt, gte, lte
    threshold: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    window_seconds: Mapped[int] = mapped_column(
        Integer,
        default=120,
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        String(50),
        default="high",
        nullable=False,
    )  # critical, high, medium, low
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    service: Mapped["Service"] = relationship(
        "Service",
        back_populates="alert_configs",
    )


class DeploymentEvent(Base):
    """
    Tracks application deployments for evidence correlation during incidents.
    """
    __tablename__ = "deployment_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
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
    )
    commit_sha: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    deployed_by: Mapped[str] = mapped_column(
        String(100),
        default="CI/CD Pipeline",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="success",
        nullable=False,
    )  # success, rolled_back, failed
    manifest_summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    deployed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    service: Mapped["Service"] = relationship(
        "Service",
        back_populates="deployment_events",
    )


class RecoveryPolicy(Base, TimestampMixin):
    """
    Governance policies regulating allowlisted recovery operations.
    """
    __tablename__ = "recovery_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    service_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("services.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )  # allowlisted operation key
    approval_required: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    cooldown_seconds: Mapped[int] = mapped_column(
        Integer,
        default=900,
        nullable=False,
    )  # 15 minutes
    max_retries: Mapped[int] = mapped_column(
        Integer,
        default=2,
        nullable=False,
    )
    auto_approve_threshold: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    service: Mapped["Service"] = relationship(
        "Service",
        back_populates="recovery_policies",
    )
