"""User daily usage tracking for rate limiting."""

from datetime import date, datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, created_at_column, updated_at_column


class UserUsage(Base):
    """
    Daily usage tracking per user for rate limiting.

    Tracks requests, tokens, and pointers created each day.
    Resets daily at midnight UTC.
    """

    __tablename__ = "user_usage"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_user_usage_user_date"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    # Usage counters
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requests_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pointers_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
