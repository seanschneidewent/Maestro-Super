from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, created_at_column, updated_at_column

if TYPE_CHECKING:
    from app.models.page import Page
    from app.models.project import Project


class Discipline(Base):
    """
    A discipline grouping within a project (e.g., Architectural, Structural, MEP).
    """

    __tablename__ = "disciplines"

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
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # "architectural"
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)  # "Architectural"
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI-generated
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="disciplines",
    )
    pages: Mapped[list["Page"]] = relationship(
        "Page",
        back_populates="discipline",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
