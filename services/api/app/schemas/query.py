"""Query schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class QueryCreate(BaseModel):
    """Schema for creating a query."""

    query_text: str = Field(..., min_length=1, alias="queryText")
    project_id: str | None = Field(default=None, alias="projectId")

    model_config = ConfigDict(populate_by_name=True)


class QueryUpdate(BaseModel):
    """Schema for updating a query (mainly for AI response)."""

    response_text: str | None = Field(default=None, alias="responseText")
    referenced_pointers: list[dict[str, Any]] | None = Field(
        default=None, alias="referencedPointers"
    )
    tokens_used: int | None = Field(default=None, alias="tokensUsed")

    model_config = ConfigDict(populate_by_name=True)


class QueryResponse(BaseModel):
    """Schema for query response."""

    id: str
    user_id: str = Field(alias="userId")
    project_id: str | None = Field(default=None, alias="projectId")
    query_text: str = Field(alias="queryText")
    response_text: str | None = Field(default=None, alias="responseText")
    referenced_pointers: list[dict[str, Any]] | None = Field(
        default=None, alias="referencedPointers"
    )
    tokens_used: int | None = Field(default=None, alias="tokensUsed")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
