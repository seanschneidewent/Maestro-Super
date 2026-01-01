from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, created_at_column

if TYPE_CHECKING:
    from app.models.page import Page
    from app.models.pointer import Pointer


class PointerReference(Base):
    """
    A cross-reference from a pointer to another page.
    Captures when a pointer's content references another sheet/page.
    """

    __tablename__ = "pointer_references"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    source_pointer_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pointers.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    target_page_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pages.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    justification: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # The text that triggered this reference

    created_at: Mapped[datetime] = created_at_column()

    # Relationships
    source_pointer: Mapped["Pointer"] = relationship(
        "Pointer",
        back_populates="outbound_references",
        foreign_keys=[source_pointer_id],
    )
    target_page: Mapped["Page"] = relationship(
        "Page",
        back_populates="inbound_references",
        foreign_keys=[target_page_id],
    )
