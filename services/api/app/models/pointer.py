from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

from sqlalchemy import ARRAY, Boolean, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, created_at_column, updated_at_column

# pgvector support - only works with PostgreSQL
try:
    from pgvector.sqlalchemy import Vector

    EMBEDDING_COLUMN_TYPE = Vector(1024)
except ImportError:
    # Fallback when pgvector not available
    EMBEDDING_COLUMN_TYPE = None  # type: ignore

if TYPE_CHECKING:
    from app.models.page import Page
    from app.models.pointer_reference import PointerReference


class Pointer(Base):
    """
    A user-drawn box on a page with AI-generated analysis and vector embedding.
    """

    __tablename__ = "pointers"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    page_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pages.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)  # AI-generated
    text_spans: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), nullable=True
    )  # Extracted text elements

    # OCR data with word positions for highlighting
    # Structure: [{text, x, y, w, h, confidence}] - normalized 0-1 coords
    ocr_data: Mapped[Optional[list[dict]]] = mapped_column(
        JSONB, nullable=True
    )

    # Bounding box (normalized 0-1 or pixel coordinates)
    bbox_x: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_width: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_height: Mapped[float] = mapped_column(Float, nullable=False)

    png_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Cropped image path

    # Flag for retry queue - set when embedding generation fails
    needs_embedding: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # V3 Pass 2 enrichment pipeline
    enrichment_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True,
    )  # 'pending' | 'processing' | 'complete' | 'failed'
    cross_references: Mapped[Optional[list]] = mapped_column(
        JSONB, nullable=True,
    )  # ["S-101", "E-201", "Detail 4/A3.01"]
    enrichment_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
    )  # {"confidence": 0.95, "reground_count": 0, "last_enriched_at": "..."}

    # Vector embedding for semantic search (Voyage 1024 dimensions)
    # Note: This column type only works with PostgreSQL + pgvector extension
    # When pgvector is not available, this column is skipped entirely
    if EMBEDDING_COLUMN_TYPE is not None:
        embedding: Mapped[Optional[list[float]]] = mapped_column(
            EMBEDDING_COLUMN_TYPE,
            nullable=True,
        )

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    # Relationships
    page: Mapped["Page"] = relationship(
        "Page",
        back_populates="pointers",
    )
    # References FROM this pointer to other pages
    outbound_references: Mapped[list["PointerReference"]] = relationship(
        "PointerReference",
        back_populates="source_pointer",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="PointerReference.source_pointer_id",
    )

    @property
    def bounds(self) -> dict:
        """Return bounding box as a dictionary."""
        return {
            "x": self.bbox_x,
            "y": self.bbox_y,
            "width": self.bbox_width,
            "height": self.bbox_height,
        }
