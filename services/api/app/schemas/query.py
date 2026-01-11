"""Query schemas."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class QueryCreate(BaseModel):
    """Schema for creating a query."""

    query_text: str = Field(..., min_length=1, alias="queryText")
    project_id: str | None = Field(default=None, alias="projectId")
    session_id: str | None = Field(default=None, alias="sessionId")

    model_config = ConfigDict(populate_by_name=True)


class AgentQueryRequest(BaseModel):
    """Schema for streaming agent query request."""

    query: str = Field(..., min_length=1, description="User's question")
    session_id: str | None = Field(default=None, alias="sessionId", description="Optional session ID to group queries")
    response_mode: str = Field(default="pages", alias="responseMode", description="'pages' or 'conversational'")

    model_config = ConfigDict(populate_by_name=True)


class AgentTraceStep(BaseModel):
    """Individual step in agent trace."""

    type: Literal["reasoning", "tool_call", "tool_result"]
    content: str | None = None  # For reasoning
    tool: str | None = None  # For tool_call/tool_result
    input: dict[str, Any] | None = None  # For tool_call
    result: dict[str, Any] | None = None  # For tool_result

    model_config = ConfigDict(populate_by_name=True)


class AgentUsage(BaseModel):
    """Token usage for agent query."""

    input_tokens: int = Field(alias="inputTokens")
    output_tokens: int = Field(alias="outputTokens")

    model_config = ConfigDict(populate_by_name=True)


class QueryUpdate(BaseModel):
    """Schema for updating a query (mainly for AI response)."""

    response_text: str | None = Field(default=None, alias="responseText")
    display_title: str | None = Field(default=None, alias="displayTitle")
    referenced_pointers: list[dict[str, Any]] | None = Field(
        default=None, alias="referencedPointers"
    )
    tokens_used: int | None = Field(default=None, alias="tokensUsed")

    model_config = ConfigDict(populate_by_name=True)


class QueryPageResponse(BaseModel):
    """Schema for query page junction response."""

    id: str | UUID
    page_id: str | UUID = Field(alias="pageId")
    page_order: int = Field(alias="pageOrder")
    pointers_shown: list[dict[str, Any]] | None = Field(
        default=None, alias="pointersShown"
    )
    # Page details (populated via relationship)
    page_name: str | None = Field(default=None, alias="pageName")
    file_path: str | None = Field(default=None, alias="filePath")
    discipline_id: str | UUID | None = Field(default=None, alias="disciplineId")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_serializer("id", "page_id", "discipline_id")
    def serialize_uuid(self, value: str | UUID | None) -> str | None:
        """Convert UUID to string for JSON serialization."""
        if value is None:
            return None
        return str(value)


class QueryResponse(BaseModel):
    """Schema for query response."""

    id: str | UUID
    user_id: str = Field(alias="userId")
    project_id: str | UUID | None = Field(default=None, alias="projectId")
    session_id: str | UUID | None = Field(default=None, alias="sessionId")
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
        validation_alias="query_pages",  # Map from model attribute
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_serializer("id", "project_id", "session_id")
    def serialize_uuid(self, value: str | UUID | None) -> str | None:
        """Convert UUID to string for JSON serialization."""
        if value is None:
            return None
        return str(value)
