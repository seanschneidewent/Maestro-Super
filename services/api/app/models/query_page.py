from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, JSONVariant

if TYPE_CHECKING:
    from app.models.page import Page
    from app.models.query import Query


class QueryPage(Base):
    """
    Junction table linking queries to pages with ordering.

    Tracks which pages were shown for a query and in what order,
    along with which pointers were highlighted on each page.
    """

    __tablename__ = "query_pages"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    query_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("queries.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    page_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("pages.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    page_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    # Pointer IDs that were highlighted on this page for this query
    # Structure: [{pointer_id: str, ...}]
    pointers_shown: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(
        JSONVariant,
        nullable=True,
    )

    # Relationships
    query: Mapped["Query"] = relationship(
        "Query",
        back_populates="query_pages",
    )
    page: Mapped["Page"] = relationship(
        "Page",
        back_populates="query_pages",
        lazy="joined",  # Eagerly load page details
    )

    # Properties to expose page details
    @property
    def page_name(self) -> str | None:
        """Get page name from relationship."""
        return self.page.page_name if self.page else None

    @property
    def file_path(self) -> str | None:
        """Get file path from relationship."""
        return self.page.file_path if self.page else None

    @property
    def discipline_id(self) -> str | None:
        """Get discipline ID from relationship."""
        return self.page.discipline_id if self.page else None
