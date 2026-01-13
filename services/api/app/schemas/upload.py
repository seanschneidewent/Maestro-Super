"""Upload schemas for bulk project creation."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DisciplineCode = Literal[
    "architectural",
    "structural",
    "mep",
    "civil",
    "kitchen",
    "vapor_mitigation",
    "canopy",
    "unknown",
]


class PageUploadData(BaseModel):
    """Data for a single page to be created."""

    page_name: str = Field(..., min_length=1, max_length=100, alias="pageName")
    file_name: str = Field(..., min_length=1, max_length=255, alias="fileName")
    storage_path: str = Field(..., min_length=1, max_length=500, alias="storagePath")

    model_config = ConfigDict(populate_by_name=True)


class DisciplineUploadData(BaseModel):
    """Data for a discipline with its pages."""

    code: DisciplineCode
    display_name: str = Field(..., min_length=1, max_length=100, alias="displayName")
    pages: list[PageUploadData]

    model_config = ConfigDict(populate_by_name=True)


class BulkUploadRequest(BaseModel):
    """Request to create a project with disciplines and pages in bulk."""

    project_name: str = Field(..., min_length=1, max_length=255, alias="projectName")
    disciplines: list[DisciplineUploadData]

    model_config = ConfigDict(populate_by_name=True)


class PageInDisciplineResponse(BaseModel):
    """Page response nested in discipline (simplified)."""

    id: str
    page_name: str = Field(alias="pageName")
    file_path: str = Field(alias="filePath")
    page_index: int = Field(default=0, alias="pageIndex")  # Zero-based index within multi-page PDF
    processed_pass_1: bool = Field(alias="processedPass1")
    processed_pass_2: bool = Field(alias="processedPass2")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid_to_str(cls, v: Any) -> str:
        """Convert UUID to string if needed."""
        return str(v) if v is not None else v


class DisciplineWithPagesResponse(BaseModel):
    """Discipline with nested pages."""

    id: str
    project_id: str = Field(alias="projectId")
    name: str
    display_name: str = Field(alias="displayName")
    processed: bool
    pages: list[PageInDisciplineResponse]

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_validator("id", "project_id", mode="before")
    @classmethod
    def convert_uuid_to_str(cls, v: Any) -> str:
        """Convert UUID to string if needed."""
        return str(v) if v is not None else v


class ProjectInUploadResponse(BaseModel):
    """Project response for upload endpoint."""

    id: str
    name: str
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid_to_str(cls, v: Any) -> str:
        """Convert UUID to string if needed."""
        return str(v) if v is not None else v


class BulkUploadResponse(BaseModel):
    """Response from bulk upload."""

    project: ProjectInUploadResponse
    disciplines: list[DisciplineWithPagesResponse]

    model_config = ConfigDict(populate_by_name=True)
