from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, created_at_column, updated_at_column
from app.models.enums import ProjectStatus

if TYPE_CHECKING:
    from app.models.discipline_context import DisciplineContext
    from app.models.project_file import ProjectFile
    from app.models.query import Query


class Project(Base):
    """
    User project containing PDF files for analysis.

    Access: Direct via user_id.
    """

    __tablename__ = "projects"

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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(
        SAEnum(ProjectStatus, native_enum=False),
        default=ProjectStatus.SETUP,
        nullable=False,
    )

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    # Relationships
    files: Mapped[list["ProjectFile"]] = relationship(
        "ProjectFile",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    discipline_contexts: Mapped[list["DisciplineContext"]] = relationship(
        "DisciplineContext",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    queries: Mapped[list["Query"]] = relationship(
        "Query",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
