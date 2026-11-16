"""
AutoHeal DevOps — Base Declarative Model & Mixins
"""

from datetime import datetime, timezone
import uuid
from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """Returns the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy 2.x models."""
    pass


class TimestampMixin:
    """Reusable timestamp mixin tracking creation and last update in UTC."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
