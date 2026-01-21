"""ProcessingJob model for tracking background sheet-analyzer processing."""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, created_at_column, updated_at_column


class ProcessingJob(Base):
    """
    Tracks background processing jobs for projects.

    Status flow: pending -> processing -> completed/failed
    """

    __tablename__ = "processing_jobs"

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
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )  # pending | processing | completed | failed

    total_pages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_pages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    current_page_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    current_page_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    # Relationship to project
    project = relationship("Project", back_populates="processing_jobs")
