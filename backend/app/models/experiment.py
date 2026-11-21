"""
AutoHeal DevOps — Phase 14 Experiment & Benchmark Models
Supports reproducible evaluation, experiment automation, and benchmarking.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, utc_now

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class Experiment(Base, TimestampMixin):
    """
    Persistent experiment definition and benchmark configuration.
    Governed by strict organization tenant isolation.
    """
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
    )  # e.g. "EXP-7A2F8B" or UUID
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )
    scenario_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )  # healthy_baseline, service_unavailable, high_error_rate, resource_exhaustion, repeated_alerts, verification_failure, unauthorized_recovery, unapproved_recovery
    execution_mode: Mapped[str] = mapped_column(
        String(50),
        default="SIMULATED",
        nullable=False,
    )  # Always SIMULATED in compliance with RECOVERY_SIMULATION_MODE=true
    recovery_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    target_service_id: Mapped[str] = mapped_column(
        String(100),
        default="checkout-api",
        nullable=False,
    )
    number_of_runs: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
    )
    random_seed: Mapped[int] = mapped_column(
        Integer,
        default=42,
        nullable=False,
    )
    configuration: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    test_conditions: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
        index=True,
    )  # pending, running, completed, failed, cancelled
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    results_summary: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    # Relationships
    runs: Mapped[List["ExperimentRun"]] = relationship(
        "ExperimentRun",
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="ExperimentRun.run_number",
        lazy="selectin",
    )
    organization: Mapped["Organization"] = relationship("Organization")
    created_by: Mapped[Optional["User"]] = relationship("User")


class ExperimentRun(Base, TimestampMixin):
    """
    Individual execution run of an experiment.
    Captures raw timestamps, metrics, simulated recovery verification, and telemetry.
    """
    __tablename__ = "experiment_runs"

    id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
    )  # e.g. "RUN-B4C1D9" or UUID
    experiment_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    run_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
        index=True,
    )  # pending, running, completed, failed, cancelled
    recovery_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    seed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Lifecycle Timestamps
    fault_injected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    detected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    recovery_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    recovery_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    health_restored_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Performance Metrics
    detection_latency_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    recovery_duration_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    total_outage_duration_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    # Verification and Safety Flags
    recovery_attempted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    recovery_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    recovery_success: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    is_false_positive: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    safety_compliant: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    escalated: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Artifact References
    incident_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    recovery_action_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    evidence_classification: Mapped[str] = mapped_column(
        String(50),
        default="SIMULATED",
        nullable=False,
    )  # MEASURED, CALCULATED, SYNTHETIC, SIMULATED

    # Structured Data
    telemetry_samples: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    execution_log: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    experiment: Mapped["Experiment"] = relationship(
        "Experiment",
        back_populates="runs",
    )
