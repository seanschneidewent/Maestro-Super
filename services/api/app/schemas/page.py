"""Page schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PageCreate(BaseModel):
    """Schema for creating a page."""

    page_name: str = Field(..., min_length=1, max_length=100, alias="pageName")  # "A1.01"
    file_path: str = Field(..., min_length=1, max_length=500, alias="filePath")

    model_config = ConfigDict(populate_by_name=True)


class PageUpdate(BaseModel):
    """Schema for updating a page."""

    page_name: str | None = Field(default=None, min_length=1, max_length=100, alias="pageName")
    file_path: str | None = Field(default=None, min_length=1, max_length=500, alias="filePath")
    initial_context: str | None = Field(default=None, alias="initialContext")
    full_context: str | None = Field(default=None, alias="fullContext")
    processed_pass_1: bool | None = Field(default=None, alias="processedPass1")
    processed_pass_2: bool | None = Field(default=None, alias="processedPass2")

    model_config = ConfigDict(populate_by_name=True)


class PageResponse(BaseModel):
    """Schema for page response."""

    id: str
    discipline_id: str = Field(alias="disciplineId")
    page_name: str = Field(alias="pageName")
    file_path: str = Field(alias="filePath")
    initial_context: str | None = Field(default=None, alias="initialContext")
    full_context: str | None = Field(default=None, alias="fullContext")
    processed_pass_1: bool = Field(alias="processedPass1")
    processed_pass_2: bool = Field(alias="processedPass2")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
