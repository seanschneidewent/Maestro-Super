from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, created_at_column
from app.models.enums import FileType

if TYPE_CHECKING:
    from app.models.context_pointer import ContextPointer
    from app.models.page_context import PageContext
    from app.models.project import Project


class ProjectFile(Base):
    """
    File or folder within a project.

    Supports nested folder hierarchy via self-referential parent_id.
    Access: Via project_id → projects.user_id.
    """

    __tablename__ = "project_files"

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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[FileType] = mapped_column(
        SAEnum(FileType, native_enum=False),
        nullable=False,
    )

    # Storage
    storage_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Folder hierarchy (self-referential)
    is_folder: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("project_files.id", ondelete="CASCADE"),
        nullable=True,
    )

    created_at: Mapped[datetime] = created_at_column()

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="files",
    )

    # Self-referential relationship for folder hierarchy
    parent: Mapped["ProjectFile | None"] = relationship(
        "ProjectFile",
        back_populates="children",
        remote_side=[id],
    )
    children: Mapped[list["ProjectFile"]] = relationship(
        "ProjectFile",
        back_populates="parent",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Related entities
    context_pointers: Mapped[list["ContextPointer"]] = relationship(
        "ContextPointer",
        back_populates="file",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    page_contexts: Mapped[list["PageContext"]] = relationship(
        "PageContext",
        back_populates="file",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
