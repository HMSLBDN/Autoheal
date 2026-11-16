"""
AutoHeal DevOps — Security & Operational Audit Log Model
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
import uuid
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class AuditLog(Base):
    """
    Immutable regulatory audit trail logging operations, approvals, and mutations.
    """
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    action: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )  # e.g. "recovery_approved", "policy_modified", "user_login"
    resource_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # service, incident, recovery, policy, user
    resource_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    details: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )  # JSON-serialized context or diff
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
        nullable=False,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="audit_logs",
    )
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="audit_logs",
    )
