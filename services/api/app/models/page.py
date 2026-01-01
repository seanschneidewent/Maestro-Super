from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, created_at_column, updated_at_column

if TYPE_CHECKING:
    from app.models.discipline import Discipline
    from app.models.pointer import Pointer
    from app.models.pointer_reference import PointerReference


class Page(Base):
    """
    A single page/sheet within a discipline (e.g., A1.01).
    """

    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    discipline_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("disciplines.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    page_name: Mapped[str] = mapped_column(String(100), nullable=False)  # "A1.01"
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)  # Storage path
    initial_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Pass 1 AI summary
    full_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Pass 2 AI summary
    processed_pass_1: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed_pass_2: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    # Relationships
    discipline: Mapped["Discipline"] = relationship(
        "Discipline",
        back_populates="pages",
    )
    pointers: Mapped[list["Pointer"]] = relationship(
        "Pointer",
        back_populates="page",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # References pointing TO this page
    inbound_references: Mapped[list["PointerReference"]] = relationship(
        "PointerReference",
        back_populates="target_page",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="PointerReference.target_page_id",
    )
