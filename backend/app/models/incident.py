"""
AutoHeal DevOps — Incident, Evidence & Timeline Event Models
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
import uuid
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, utc_now

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.service import Service
    from app.models.recovery import RecoveryAction
    from app.models.user import User


class Incident(Base, TimestampMixin):
    """
    Incident entity capturing detected operational breaches, AI diagnosis,
    correlated evidence, and event timelines.
    """
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_org_detected_at", "organization_id", "detected_at"),
        Index("ix_incidents_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
    )  # e.g. "INC-2841" or UUID
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
    service_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        String(50),
        default="high",
        index=True,
        nullable=False,
    )  # critical, high, medium, low
    status: Mapped[str] = mapped_column(
        String(50),
        default="open",
        index=True,
        nullable=False,
    )  # open, investigating, recovering, resolved
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
        nullable=False,
    )
    recovery_status: Mapped[str] = mapped_column(
        String(100),
        default="Not started",
        nullable=False,
    )
    error_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    threshold: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        nullable=False,
    )
    probable_cause: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )
    recommended_action: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="incidents",
    )
    service: Mapped["Service"] = relationship(
        "Service",
        back_populates="incidents",
    )
    evidence: Mapped[List["IncidentEvidence"]] = relationship(
        "IncidentEvidence",
        back_populates="incident",
        cascade="all, delete-orphan",
    )
    events: Mapped[List["IncidentEvent"]] = relationship(
        "IncidentEvent",
        back_populates="incident",
        cascade="all, delete-orphan",
    )
    recovery_actions: Mapped[List["RecoveryAction"]] = relationship(
        "RecoveryAction",
        back_populates="incident",
        cascade="all, delete-orphan",
    )
    transitions: Mapped[List["IncidentTransition"]] = relationship(
        "IncidentTransition",
        back_populates="incident",
        cascade="all, delete-orphan",
    )


class IncidentEvidence(Base):
    """
    Correlated signal evidence supporting an incident diagnosis.
    """
    __tablename__ = "incident_evidence"

    id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
        default=lambda: f"ev-{uuid.uuid4().hex[:8]}",
    )
    incident_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # metric, log, deployment, health_check
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    detail: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
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
    incident: Mapped["Incident"] = relationship(
        "Incident",
        back_populates="evidence",
    )


class IncidentEvent(Base):
    """
    Historical timeline event attached to an incident.
    """
    __tablename__ = "incident_events"

    id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
        default=lambda: f"evt-{uuid.uuid4().hex[:8]}",
    )
    incident_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    label: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    detail: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    tone: Mapped[str] = mapped_column(
        String(50),
        default="neutral",
        nullable=False,
    )  # neutral, warning, success
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    incident: Mapped["Incident"] = relationship(
        "Incident",
        back_populates="events",
    )


class IncidentTransition(Base, TimestampMixin):
    """
    Tamper-evident audit trail for incident lifecycle state transitions.
    Records acting user, timestamp, previous_state, new_state, reason, evidence_id, sign_off.
    """
    __tablename__ = "incident_transitions"

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
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    actor_role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    previous_state: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    new_state: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    evidence_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    sign_off: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    incident: Mapped["Incident"] = relationship(
        "Incident",
        back_populates="transitions",
    )
