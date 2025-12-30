"""DisciplineContext schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DisciplineStatus


class DisciplineContextCreate(BaseModel):
    """Schema for creating a discipline context."""

    code: str = Field(..., min_length=1, max_length=5)
    name: str = Field(..., min_length=1, max_length=100)

    model_config = ConfigDict(populate_by_name=True)


class DisciplineContextUpdate(BaseModel):
    """Schema for updating a discipline context."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    context_description: str | None = Field(default=None, alias="contextDescription")
    key_contents: dict[str, Any] | None = Field(default=None, alias="keyContents")
    connections: dict[str, Any] | None = None
    processing_status: DisciplineStatus | None = Field(
        default=None, alias="processingStatus"
    )

    model_config = ConfigDict(populate_by_name=True)


class DisciplineContextResponse(BaseModel):
    """Schema for discipline context response."""

    id: str
    project_id: str = Field(alias="projectId")
    code: str
    name: str
    context_description: str | None = Field(default=None, alias="contextDescription")
    key_contents: dict[str, Any] | None = Field(default=None, alias="keyContents")
    connections: dict[str, Any] | None = None
    processing_status: DisciplineStatus = Field(alias="processingStatus")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
