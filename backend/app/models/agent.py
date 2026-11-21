"""
AutoHeal DevOps — Infrastructure Agent Database Model
Represents registered remote or local infrastructure agents bound to tenant organizations.
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
import uuid
import json

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, utc_now

if TYPE_CHECKING:
    from app.models.organization import Organization


class InfrastructureAgent(Base, TimestampMixin):
    """
    Dedicated infrastructure execution agent.
    Receives cryptographically signed action envelopes and enforces strict allowlists.
    """
    __tablename__ = "infrastructure_agents"
    __table_args__ = (
        Index("ix_agents_org_env", "organization_id", "environment"),
        Index("ix_agents_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )  # e.g. "agent-node-01" or UUID string
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    hostname: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    ip_address: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    environment: Mapped[str] = mapped_column(
        String(50),
        default="production",
        index=True,
        nullable=False,
    )  # production, staging, local
    status: Mapped[str] = mapped_column(
        String(50),
        default="online",
        index=True,
        nullable=False,
    )  # online, busy, degraded, offline, revoked
    version: Mapped[str] = mapped_column(
        String(50),
        default="1.0.0",
        nullable=False,
    )
    capabilities_json: Mapped[str] = mapped_column(
        Text,
        default='["restart_service", "scale_service", "clear_cache", "health_check"]',
        nullable=False,
    )
    public_key_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    secret_key_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    last_heartbeat: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="infrastructure_agents",
    )

    @property
    def capabilities(self) -> List[str]:
        """Parsed list of supported capabilities."""
        try:
            return json.loads(self.capabilities_json)
        except Exception:
            return ["restart_service", "health_check"]

    @capabilities.setter
    def capabilities(self, value: List[str]) -> None:
        self.capabilities_json = json.dumps(value)
