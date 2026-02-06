"""Maestro session model — persistent session state for V3."""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, created_at_column, updated_at_column


class MaestroSession(Base):
    """
    A persistent Maestro session.

    Sessions hold the hot-layer conversation state (Maestro + Learning messages)
    and workspace state. They are checkpointed from in-memory to Supabase
    periodically for resilience against server restarts.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "session_type IN ('workspace', 'telegram')",
            name="ck_sessions_session_type",
        ),
        CheckConstraint(
            "status IN ('active', 'idle', 'closed')",
            name="ck_sessions_status",
        ),
        Index("idx_sessions_project", "project_id"),
        Index("idx_sessions_user", "user_id"),
        Index(
            "idx_sessions_active",
            "status",
            postgresql_where="status = 'active'",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    session_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )  # 'workspace' | 'telegram'

    # Workspace identity (NULL for telegram sessions)
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True,
    )
    workspace_name: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )

    # Conversation state (checkpointed from in-memory)
    maestro_messages: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
        server_default="[]",
    )
    learning_messages: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
        server_default="[]",
    )

    # Workspace state (NULL for telegram sessions)
    workspace_state: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
        default=lambda: {"displayed_pages": [], "highlighted_pointers": [], "pinned_pages": []},
    )

    # Lifecycle
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active",
        server_default="active",
    )
    last_active_at: Mapped[datetime] = created_at_column()  # defaults to now()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
