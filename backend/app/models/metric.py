"""
AutoHeal DevOps — Service Telemetry Metrics Model
"""

from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.service import Service


class ServiceMetric(Base):
    """
    Time-series metric sample captured for a monitored infrastructure service.
    """
    __tablename__ = "service_metrics"
    __table_args__ = (
        Index("ix_service_metrics_svc_sampled", "service_id", "sampled_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    service_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("services.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    sampled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
        nullable=False,
    )
    cpu_percent: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    memory_percent: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    request_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    error_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    latency_ms: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    availability: Mapped[float] = mapped_column(
        Float,
        default=100.0,
        nullable=False,
    )

    # Relationships
    service: Mapped["Service"] = relationship(
        "Service",
        back_populates="metrics",
    )
