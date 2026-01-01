from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, created_at_column, updated_at_column

if TYPE_CHECKING:
    from app.models.discipline import Discipline
    from app.models.query import Query


class Project(Base):
    """
    User project containing construction plans for analysis.
    """

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    # Relationships
    disciplines: Mapped[list["Discipline"]] = relationship(
        "Discipline",
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
