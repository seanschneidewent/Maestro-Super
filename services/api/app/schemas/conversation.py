"""Conversation schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class QueryPageResponse(BaseModel):
    """Schema for query page junction response (legacy)."""

    id: str | UUID
    page_id: str | UUID = Field(alias="pageId")
    page_order: int = Field(alias="pageOrder")
    pointers_shown: list[dict[str, Any]] | None = Field(
        default=None, alias="pointersShown"
    )
    page_name: str | None = Field(default=None, alias="pageName")
    file_path: str | None = Field(default=None, alias="filePath")
    discipline_id: str | UUID | None = Field(default=None, alias="disciplineId")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_serializer("id", "page_id", "discipline_id")
    def serialize_uuid(self, value: str | UUID | None) -> str | None:
        if value is None:
            return None
        return str(value)


class QueryResponse(BaseModel):
    """Schema for query response (legacy)."""

    id: str | UUID
    user_id: str = Field(alias="userId")
    project_id: str | UUID | None = Field(default=None, alias="projectId")
    conversation_id: str | UUID | None = Field(default=None, alias="conversationId")
    query_text: str = Field(alias="queryText")
    response_text: str | None = Field(default=None, alias="responseText")
    display_title: str | None = Field(default=None, alias="displayTitle")
    sequence_order: int | None = Field(default=None, alias="sequenceOrder")
    referenced_pointers: list[dict[str, Any]] | None = Field(
        default=None, alias="referencedPointers"
    )
    trace: list[dict[str, Any]] | None = Field(default=None)
    tokens_used: int | None = Field(default=None, alias="tokensUsed")
    created_at: datetime = Field(alias="createdAt")
    pages: list[QueryPageResponse] = Field(
        default_factory=list,
        validation_alias="query_pages",
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_serializer("id", "project_id", "conversation_id")
    def serialize_uuid(self, value: str | UUID | None) -> str | None:
        if value is None:
            return None
        return str(value)


class ConversationCreate(BaseModel):
    """Schema for creating a conversation."""

    project_id: str = Field(..., alias="projectId")

    model_config = ConfigDict(populate_by_name=True)


class ConversationResponse(BaseModel):
    """Schema for conversation response."""

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


class ConversationWithQueries(ConversationResponse):
    """Conversation response including ordered queries."""

    queries: list[QueryResponse] = Field(default_factory=list)
