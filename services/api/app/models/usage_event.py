from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Enum as SAEnum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, JSONVariant, created_at_column
from app.models.enums import EventType


class UsageEvent(Base):
    """
    Usage tracking for billing.

    Logs every AI API call with token counts and costs.
    Access: Direct via user_id.
    """

    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        index=True,
        nullable=False,
    )

    # Event details
    event_type: Mapped[EventType] = mapped_column(
        SAEnum(EventType, native_enum=False),
        nullable=False,
    )

    # Token usage
    tokens_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Cost tracking (in cents)
    cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Additional context
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONVariant,
        nullable=True,
    )

    created_at: Mapped[datetime] = created_at_column()
