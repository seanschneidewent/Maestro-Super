from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, created_at_column, updated_at_column

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.query import Query


class Session(Base):
    """
    A session groups related queries within a project.

    Sessions provide continuity for multi-turn conversations
    and allow restoring previous query states.
    """

    __tablename__ = "sessions"

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
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="sessions",
    )
    queries: Mapped[list["Query"]] = relationship(
        "Query",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Query.sequence_order",
    )
