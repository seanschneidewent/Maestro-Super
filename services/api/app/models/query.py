from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, JSONVariant, created_at_column

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.query_page import QueryPage
    from app.models.conversation import Conversation


class Query(Base):
    """
    Query history with AI responses.

    Stores user queries, Claude responses, and referenced context.
    """

    __tablename__ = "queries"

    # Note: Using UUID to match production database schema
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )
    project_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    conversation_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    # Query content
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Display title for UI (e.g., "Electrical panel locations")
    display_title: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Order within conversation (1, 2, 3, ...)
    sequence_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Context used for response
    referenced_pointers: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(
        JSONVariant,
        nullable=True,
    )

    # Full execution trace (reasoning, tool calls, tool results)
    trace: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(
        JSONVariant,
        nullable=True,
    )

    # Usage metrics
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Soft delete flag
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = created_at_column()

    # Relationships
    project: Mapped[Optional["Project"]] = relationship(
        "Project",
        back_populates="queries",
    )
    conversation: Mapped[Optional["Conversation"]] = relationship(
        "Conversation",
        back_populates="queries",
    )
    query_pages: Mapped[list["QueryPage"]] = relationship(
        "QueryPage",
        back_populates="query",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QueryPage.page_order",
    )
