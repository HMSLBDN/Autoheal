"""
AutoHeal DevOps — Recovery Action & Verification Result Models
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
import uuid
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, utc_now

if TYPE_CHECKING:
    from app.models.incident import Incident
    from app.models.service import Service
    from app.models.user import User


class RecoveryAction(Base, TimestampMixin):
    """
    Controlled recovery workflow instance triggered by policy or operator.
    """
    __tablename__ = "recovery_actions"

    id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
    )  # e.g. "REC-611" or UUID
    incident_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("incidents.id", ondelete="CASCADE"),
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
    action: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )  # e.g. "Rollback to previous stable release"
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending_approval",
        index=True,
        nullable=False,
    )  # pending_approval, approved, running, completed, failed, rejected
    approval_required: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    requested_by: Mapped[str] = mapped_column(
        String(100),
        default="AutoHeal policy",
        nullable=False,
    )
    approver_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
        nullable=False,
    )
    duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    verification: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
    )  # pending, passed, failed, not_started
    execution_mode: Mapped[str] = mapped_column(
        String(50),
        default="SIMULATED",
        nullable=False,
    )  # SIMULATED, REAL
    evidence_classification: Mapped[str] = mapped_column(
        String(50),
        default="SIMULATED",
        nullable=False,
    )  # SIMULATED, DOCKER_API_ACCEPTED, HEALTH_VERIFIED, VERIFICATION_FAILED

    # Relationships
    incident: Mapped["Incident"] = relationship(
        "Incident",
        back_populates="recovery_actions",
    )
    service: Mapped["Service"] = relationship(
        "Service",
        back_populates="recovery_actions",
    )
    approver: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="approved_recoveries",
    )
    result: Mapped[Optional["RecoveryResult"]] = relationship(
        "RecoveryResult",
        back_populates="recovery_action",
        uselist=False,
        cascade="all, delete-orphan",
    )


class RecoveryResult(Base):
    """
    Verification outcome and diagnostic audit log for an executed recovery.
    """
    __tablename__ = "recovery_results"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    recovery_action_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("recovery_actions.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    diagnostic_output: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    execution_mode: Mapped[str] = mapped_column(
        String(50),
        default="SIMULATED",
        nullable=False,
    )  # SIMULATED, REAL
    evidence_classification: Mapped[str] = mapped_column(
        String(50),
        default="SIMULATED",
        nullable=False,
    )  # SIMULATED, DOCKER_API_ACCEPTED, HEALTH_VERIFIED, VERIFICATION_FAILED
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    # Relationships
    recovery_action: Mapped["RecoveryAction"] = relationship(
        "RecoveryAction",
        back_populates="result",
    )
