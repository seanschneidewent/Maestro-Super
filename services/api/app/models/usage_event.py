from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, JSONVariant, created_at_column


class UsageEvent(Base):
    """
    Usage tracking for billing.

    Logs every AI API call with token counts and costs.
    """

    __tablename__ = "usage_events"

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

    # Event type: 'gemini_extraction', 'claude_query', 'ocr_page', 'voyage_embedding'
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # Token usage
    tokens_input: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Cost tracking (in cents)
    cost_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Additional context (named event_metadata to avoid SQLAlchemy reserved name)
    event_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata",  # Column name in DB stays as 'metadata'
        JSONVariant,
        nullable=True,
    )

    created_at: Mapped[datetime] = created_at_column()
