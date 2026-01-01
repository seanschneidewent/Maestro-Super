from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from sqlalchemy import ARRAY, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, created_at_column, updated_at_column

# pgvector support - only works with PostgreSQL
try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False
    Vector = None

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

    # Bounding box (normalized 0-1 or pixel coordinates)
    bbox_x: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_width: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_height: Mapped[float] = mapped_column(Float, nullable=False)

    png_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Cropped image path

    # Vector embedding for semantic search (Voyage 1024 dimensions)
    # Note: This column type only works with PostgreSQL + pgvector extension
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(1024) if HAS_PGVECTOR else None,
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
