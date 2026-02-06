"""Telegram user mapping model — links Telegram users to Maestro users and projects."""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, created_at_column


class TelegramUser(Base):
    """
    Maps a Telegram user to a Maestro user and project.

    For v1, each Telegram user is associated with one project. This allows
    the Telegram bot to know which project context to use when a user messages.
    Future versions may support multiple projects per Telegram user via
    self-service linking in the web app.
    """

    __tablename__ = "telegram_users"

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = created_at_column()
