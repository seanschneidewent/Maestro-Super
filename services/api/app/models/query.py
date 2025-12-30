from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, JSONVariant, created_at_column

if TYPE_CHECKING:
    from app.models.project import Project


class Query(Base):
    """
    Query history with AI responses.

    Stores user queries, Claude responses, and referenced context.
    Access: Direct via user_id (also linked to project_id).
    """

    __tablename__ = "queries"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        index=True,
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Query content
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Context used for response
    referenced_pointers: Mapped[dict[str, Any] | None] = mapped_column(
        JSONVariant,
        nullable=True,
    )

    # Usage metrics
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = created_at_column()

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="queries",
    )
