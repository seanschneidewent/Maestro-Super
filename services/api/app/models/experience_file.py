"""Experience file model — Learning's filesystem stored as rows."""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, created_at_column, updated_at_column


class ExperienceFile(Base):
    """
    A markdown file in the Experience filesystem.

    Learning agents write these to build up project knowledge over time.
    Maestro reads them every query to shape its behavior.
    Stored as rows in Supabase, but behaves like a filesystem to Learning.
    """

    __tablename__ = "experience_files"
    __table_args__ = (
        UniqueConstraint("project_id", "path", name="uq_experience_files_project_path"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    path: Mapped[str] = mapped_column(
        Text, nullable=False,
    )  # e.g. 'routing_rules.md', 'subs/concrete.md'
    content: Mapped[str] = mapped_column(
        Text, nullable=False, default="",
    )
    updated_by_session: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True,
    )  # Which session last wrote this

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
