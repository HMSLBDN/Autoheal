"""
AutoHeal DevOps — Organization (Tenant) Model
"""

from typing import TYPE_CHECKING, List
import uuid
from sqlalchemy import Boolean, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.service import Service
    from app.models.incident import Incident
    from app.models.audit import AuditLog
    from app.models.agent import InfrastructureAgent


class Organization(Base, TimestampMixin):
    """
    Tenant root entity isolating services, users, incidents, and audit logs.
    """
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    plan: Mapped[str] = mapped_column(
        String(50),
        default="starter",
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    users: Mapped[List["User"]] = relationship(
        "User",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    services: Mapped[List["Service"]] = relationship(
        "Service",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    incidents: Mapped[List["Incident"]] = relationship(
        "Incident",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    infrastructure_agents: Mapped[List["InfrastructureAgent"]] = relationship(
        "InfrastructureAgent",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
