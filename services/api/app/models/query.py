from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
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
    """

    __tablename__ = "queries"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )

    # Query content
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Context used for response
    referenced_pointers: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONVariant,
        nullable=True,
    )

    # Usage metrics
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = created_at_column()

    # Relationships
    project: Mapped[Optional["Project"]] = relationship(
        "Project",
        back_populates="queries",
    )
