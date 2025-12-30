from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# JSONVariant: Uses JSONB on PostgreSQL, plain JSON on SQLite
JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    type_annotation_map = {
        dict[str, Any]: JSONVariant,
    }


def utc_now() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc)


# Common column factories for consistent timestamp handling
def created_at_column() -> Mapped[datetime]:
    """Create a created_at column with cross-database compatibility."""
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # Works on PostgreSQL
        default=utc_now,  # Fallback for SQLite
        nullable=False,
    )


def updated_at_column() -> Mapped[datetime]:
    """Create an updated_at column with cross-database compatibility."""
    return mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
