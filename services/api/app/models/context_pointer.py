from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Enum as SAEnum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, JSONVariant, created_at_column
from app.models.enums import PointerStatus

if TYPE_CHECKING:
    from app.models.project_file import ProjectFile


class ContextPointer(Base):
    """
    User-drawn box on a PDF page with AI-enriched metadata.

    Stores normalized coordinates (0-1 space) that render correctly
    at any zoom level or container size.

    Access: Via file_id → project_files.project_id → projects.user_id.
    """

    __tablename__ = "context_pointers"
    __table_args__ = (
        Index("ix_context_pointer_file_page", "file_id", "page_number"),
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

    # Normalized bounds (0-1 coordinate space)
    x_norm: Mapped[float] = mapped_column(Float, nullable=False)
    y_norm: Mapped[float] = mapped_column(Float, nullable=False)
    w_norm: Mapped[float] = mapped_column(Float, nullable=False)
    h_norm: Mapped[float] = mapped_column(Float, nullable=False)

    # Content
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # AI Analysis (from Gemini)
    ai_technical_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_trade_category: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )
    ai_elements: Mapped[dict[str, Any] | None] = mapped_column(
        JSONVariant,
        nullable=True,
    )
    ai_measurements: Mapped[dict[str, Any] | None] = mapped_column(
        JSONVariant,
        nullable=True,
    )
    ai_recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_issues: Mapped[dict[str, Any] | None] = mapped_column(
        JSONVariant,
        nullable=True,
    )

    # Extracted text (hybrid OCR)
    text_content: Mapped[dict[str, Any] | None] = mapped_column(
        JSONVariant,
        nullable=True,
    )

    # Status
    status: Mapped[PointerStatus] = mapped_column(
        SAEnum(PointerStatus, native_enum=False),
        default=PointerStatus.GENERATING,
        nullable=False,
    )
    committed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )

    created_at: Mapped[datetime] = created_at_column()

    # Relationships
    file: Mapped["ProjectFile"] = relationship(
        "ProjectFile",
        back_populates="context_pointers",
    )

    @property
    def bounds(self) -> dict[str, float]:
        """Return bounds as a dictionary matching frontend interface."""
        return {
            "xNorm": self.x_norm,
            "yNorm": self.y_norm,
            "wNorm": self.w_norm,
            "hNorm": self.h_norm,
        }

    @property
    def is_committed(self) -> bool:
        """Check if pointer has been committed (published)."""
        return self.committed_at is not None
