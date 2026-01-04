"""Session schemas."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

if TYPE_CHECKING:
    from app.schemas.query import QueryResponse


class SessionCreate(BaseModel):
    """Schema for creating a session."""

    project_id: str = Field(..., alias="projectId")

    model_config = ConfigDict(populate_by_name=True)


class SessionResponse(BaseModel):
    """Schema for session response."""

    id: str | UUID
    user_id: str = Field(alias="userId")
    project_id: str | UUID = Field(alias="projectId")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    title: str | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_serializer("id", "project_id")
    def serialize_uuid(self, value: str | UUID | None) -> str | None:
        """Convert UUID to string for JSON serialization."""
        if value is None:
            return None
        return str(value)


class SessionWithQueries(SessionResponse):
    """Session response including ordered queries."""

    queries: list["QueryResponse"] = Field(default_factory=list)


# Avoid circular import by updating forward ref
from app.schemas.query import QueryResponse  # noqa: E402

SessionWithQueries.model_rebuild()
