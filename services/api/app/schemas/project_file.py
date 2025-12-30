"""ProjectFile schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import FileType


class ProjectFileCreate(BaseModel):
    """Schema for creating a file or folder."""

    name: str = Field(..., min_length=1, max_length=255)
    file_type: FileType = Field(alias="fileType")
    storage_path: str | None = Field(default=None, alias="storagePath")
    page_count: int | None = Field(default=None, alias="pageCount")
    is_folder: bool = Field(default=False, alias="isFolder")
    parent_id: str | None = Field(default=None, alias="parentId")

    model_config = ConfigDict(populate_by_name=True)


class ProjectFileUpdate(BaseModel):
    """Schema for updating a file."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    storage_path: str | None = Field(default=None, alias="storagePath")
    page_count: int | None = Field(default=None, alias="pageCount")
    parent_id: str | None = Field(default=None, alias="parentId")

    model_config = ConfigDict(populate_by_name=True)


class ProjectFileResponse(BaseModel):
    """Schema for file response (flat)."""

    id: str
    project_id: str = Field(alias="projectId")
    name: str
    file_type: FileType = Field(alias="fileType")
    storage_path: str | None = Field(default=None, alias="storagePath")
    page_count: int | None = Field(default=None, alias="pageCount")
    is_folder: bool = Field(alias="isFolder")
    parent_id: str | None = Field(default=None, alias="parentId")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ProjectFileTreeResponse(BaseModel):
    """
    Schema for file response with children (tree structure).

    Matches frontend ProjectFile interface.
    """

    id: str
    name: str
    type: FileType  # Frontend uses 'type' not 'file_type'
    parent_id: str | None = Field(default=None, alias="parentId")
    children: list["ProjectFileTreeResponse"] | None = None
    category: str | None = None  # For Use Mode grouping

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @classmethod
    def from_orm_with_children(
        cls, file: Any, children_map: dict[str | None, list[Any]]
    ) -> "ProjectFileTreeResponse":
        """
        Build tree structure from flat file list.

        Args:
            file: ProjectFile ORM object
            children_map: Dict mapping parent_id to list of children
        """
        children = children_map.get(file.id, [])
        return cls(
            id=file.id,
            name=file.name,
            type=file.file_type,
            parent_id=file.parent_id,
            children=[
                cls.from_orm_with_children(child, children_map) for child in children
            ]
            if children
            else None,
        )
