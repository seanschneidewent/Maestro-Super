from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Enum as SAEnum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, JSONVariant
from app.models.enums import ProcessingStatus

if TYPE_CHECKING:
    from app.models.project_file import ProjectFile


class PageContext(Base):
    """
    Page-level context from Pass 1 & 2 analysis.

    Stores sheet metadata, cross-references, and processing state.
    Access: Via file_id → project_files.project_id → projects.user_id.
    """

    __tablename__ = "page_contexts"
    __table_args__ = (
        UniqueConstraint("file_id", "page_number", name="uq_page_context_file_page"),
        Index("ix_page_context_file_page", "file_id", "page_number"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("project_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Sheet metadata
    sheet_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    discipline_code: Mapped[str | None] = mapped_column(
        String(5),
        nullable=True,
    )

    # Pass 1 output
    context_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    pass1_output: Mapped[dict[str, Any] | None] = mapped_column(
        JSONVariant,
        nullable=True,
    )

    # Pass 2 output
    pass2_output: Mapped[dict[str, Any] | None] = mapped_column(
        JSONVariant,
        nullable=True,
    )
    inbound_references: Mapped[dict[str, Any] | None] = mapped_column(
        JSONVariant,
        nullable=True,
    )

    # Processing state machine
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        SAEnum(ProcessingStatus, native_enum=False),
        default=ProcessingStatus.UNPROCESSED,
        nullable=False,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    file: Mapped["ProjectFile"] = relationship(
        "ProjectFile",
        back_populates="page_contexts",
    )
