"""Project memory files for Big Maestro learning system."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, created_at_column

if TYPE_CHECKING:
    from app.models.project import Project


class ProjectMemoryFile(Base):
    """
    Memory file storage for Big Maestro.
    
    Each project can have multiple memory files of different types:
    - core: Project truths that never change
    - routing: Where to find things in the plans
    - preferences: User communication preferences
    - memory: Conversation context and history
    - learning: Log of what's been taught
    - fast_context: Nudges for Fast mode agent
    - med_context: Nudges for Med mode agent
    - deep_context: Nudges for Deep mode agent
    """

    __tablename__ = "project_memory_files"
    __table_args__ = (
        CheckConstraint(
            "file_type IN ('core', 'routing', 'preferences', 'memory', 'learning', 'fast_context', 'med_context', 'deep_context')",
            name='valid_file_type'
        ),
        UniqueConstraint('project_id', 'file_type', name='uq_project_memory_file_type'),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    project_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_content: Mapped[str] = mapped_column(Text, default="")
    
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    project: Mapped[Optional["Project"]] = relationship("Project")


class LearningEvent(Base):
    """
    Log of learning/teaching events for Big Maestro.
    
    Tracks what was taught, how it was classified, and what was updated.
    """

    __tablename__ = "learning_events"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    project_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Event details
    event_type: Mapped[str] = mapped_column(Text, nullable=False)  # 'correction', 'teaching', 'clarification'
    classification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 'routing', 'truth', 'preference', etc.
    
    # Context
    original_query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    original_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correction_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # What was updated
    file_updated: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    update_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = created_at_column()

    # Relationships
    project: Mapped[Optional["Project"]] = relationship("Project")
