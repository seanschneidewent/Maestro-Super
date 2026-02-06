"""Benchmark log model — structured logging for emergent scoring (Phase 7)."""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, created_at_column


class BenchmarkLog(Base):
    """
    Captures structured data from every Maestro interaction for evaluation.

    Input data is logged during the Maestro turn. Learning evaluation (assessment,
    scores, updates) is filled async by the Learning agent. User signals are
    inferred from the next user message.
    """

    __tablename__ = "benchmark_logs"
    __table_args__ = (
        Index("idx_benchmark_project", "project_id"),
        Index("idx_benchmark_session", "session_id"),
        Index("idx_benchmark_model", "response_model"),
        Index("idx_benchmark_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    session_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_heartbeat: Mapped[bool] = mapped_column(Boolean, default=False)

    # Input
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    experience_paths_read: Mapped[Optional[list]] = mapped_column(
        ARRAY(Text), nullable=True
    )
    pointers_retrieved: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    workspace_actions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Output
    maestro_response: Mapped[str] = mapped_column(Text, nullable=False)
    response_model: Mapped[str] = mapped_column(Text, nullable=False)
    response_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    token_count_input: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    token_count_output: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Learning evaluation (filled async by Learning agent)
    learning_assessment: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    scoring_dimensions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    experience_updates: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    knowledge_edits: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # User signals (filled from subsequent interaction)
    user_followed_up: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    user_corrected: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    user_rephrased: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    user_moved_on: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = created_at_column()
