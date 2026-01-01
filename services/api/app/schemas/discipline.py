"""Discipline schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DisciplineCreate(BaseModel):
    """Schema for creating a discipline."""

    name: str = Field(..., min_length=1, max_length=100)  # "architectural"
    display_name: str = Field(..., min_length=1, max_length=100, alias="displayName")  # "Architectural"

    model_config = ConfigDict(populate_by_name=True)


class DisciplineUpdate(BaseModel):
    """Schema for updating a discipline."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    display_name: str | None = Field(default=None, min_length=1, max_length=100, alias="displayName")
    summary: str | None = None
    processed: bool | None = None

    model_config = ConfigDict(populate_by_name=True)


class DisciplineResponse(BaseModel):
    """Schema for discipline response."""

    id: str
    project_id: str = Field(alias="projectId")
    name: str
    display_name: str = Field(alias="displayName")
    summary: str | None = None
    processed: bool
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_validator("id", "project_id", mode="before")
    @classmethod
    def convert_uuid_to_str(cls, v: Any) -> str:
        """Convert UUID to string if needed."""
        return str(v) if v is not None else v
