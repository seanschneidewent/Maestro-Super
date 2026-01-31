from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, created_at_column, updated_at_column

if TYPE_CHECKING:
    from app.models.discipline import Discipline
    from app.models.pointer import Pointer
    from app.models.pointer_reference import PointerReference
    from app.models.query_page import QueryPage


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
    page_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # Zero-based index within source PDF
    initial_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Pass 1 AI summary
    full_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Pass 2 AI summary
    processed_pass_1: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed_pass_2: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # PNG pre-rendering pipeline fields
    page_image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Storage path to PNG
    page_image_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    full_page_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Full OCR text
    ocr_data: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)  # Word positions [{text, x, y, w, h}]
    processed_ocr: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Sheet-analyzer pipeline fields (Brain Mode)
    regions: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)  # Structural regions
    sheet_reflection: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Brain Mode reflection
    page_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # detail_sheet, plan, etc.
    cross_references: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)  # Referenced sheets

    # Deprecated (legacy OCR pipeline)
    semantic_index: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # Words with bboxes, region_type, role
    context_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Gemini-generated sheet summary
    details: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)  # Extracted detail nodes from markdown
    processing_status: Mapped[Optional[str]] = mapped_column(String(50), default="pending", nullable=True)  # pending|processing|completed|failed
    processed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)  # When processing completed

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
    # Queries that displayed this page
    query_pages: Mapped[list["QueryPage"]] = relationship(
        "QueryPage",
        back_populates="page",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
