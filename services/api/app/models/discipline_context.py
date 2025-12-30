from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Enum as SAEnum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, JSONVariant
from app.models.enums import DisciplineStatus

if TYPE_CHECKING:
    from app.models.project import Project


class DisciplineContext(Base):
    """
    Discipline-level context from Pass 3 rollup.

    Aggregates all pages in a discipline into a summary.
    Access: Via project_id → projects.user_id.
    """

    __tablename__ = "discipline_contexts"
    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_discipline_context_project_code"),
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

    # Discipline identification
    code: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Pass 3 output
    context_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_contents: Mapped[dict[str, Any] | None] = mapped_column(
        JSONVariant,
        nullable=True,
    )
    connections: Mapped[dict[str, Any] | None] = mapped_column(
        JSONVariant,
        nullable=True,
    )

    # Processing status
    processing_status: Mapped[DisciplineStatus] = mapped_column(
        SAEnum(DisciplineStatus, native_enum=False),
        default=DisciplineStatus.WAITING,
        nullable=False,
    )

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="discipline_contexts",
    )

    # Standard discipline codes and names
    DISCIPLINES = {
        "A": "Architectural",
        "S": "Structural",
        "M": "Mechanical",
        "E": "Electrical",
        "P": "Plumbing",
        "FP": "Fire Protection",
        "C": "Civil",
        "L": "Landscape",
        "G": "General",
    }

    @classmethod
    def get_discipline_name(cls, code: str) -> str:
        """Get full discipline name from code."""
        return cls.DISCIPLINES.get(code.upper(), "Unknown")
