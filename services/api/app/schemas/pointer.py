"""Pointer schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BoundingBox(BaseModel):
    """Bounding box coordinates."""

    x: float = Field(..., alias="bboxX")
    y: float = Field(..., alias="bboxY")
    width: float = Field(..., alias="bboxWidth")
    height: float = Field(..., alias="bboxHeight")

    model_config = ConfigDict(populate_by_name=True)


class PointerCreate(BaseModel):
    """Schema for creating a pointer."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    text_spans: list[str] | None = Field(default=None, alias="textSpans")
    bbox_x: float = Field(..., alias="bboxX")
    bbox_y: float = Field(..., alias="bboxY")
    bbox_width: float = Field(..., alias="bboxWidth")
    bbox_height: float = Field(..., alias="bboxHeight")
    png_path: str | None = Field(default=None, alias="pngPath")

    model_config = ConfigDict(populate_by_name=True)


class PointerUpdate(BaseModel):
    """Schema for updating a pointer."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    text_spans: list[str] | None = Field(default=None, alias="textSpans")
    bbox_x: float | None = Field(default=None, alias="bboxX")
    bbox_y: float | None = Field(default=None, alias="bboxY")
    bbox_width: float | None = Field(default=None, alias="bboxWidth")
    bbox_height: float | None = Field(default=None, alias="bboxHeight")
    png_path: str | None = Field(default=None, alias="pngPath")
    embedding: list[float] | None = None  # 1024-dim vector

    model_config = ConfigDict(populate_by_name=True)


class PointerResponse(BaseModel):
    """Schema for pointer response."""

    id: str
    page_id: str = Field(alias="pageId")
    title: str
    description: str
    text_spans: list[str] | None = Field(default=None, alias="textSpans")
    bbox_x: float = Field(alias="bboxX")
    bbox_y: float = Field(alias="bboxY")
    bbox_width: float = Field(alias="bboxWidth")
    bbox_height: float = Field(alias="bboxHeight")
    png_path: str | None = Field(default=None, alias="pngPath")
    has_embedding: bool = Field(default=False, alias="hasEmbedding")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_validator("id", "page_id", mode="before")
    @classmethod
    def convert_uuid_to_str(cls, v: Any) -> str:
        """Convert UUID to string if needed."""
        return str(v) if v is not None else v

    @classmethod
    def from_orm_with_embedding_check(cls, obj) -> "PointerResponse":
        """Create response with embedding presence check."""
        # Check if embedding attribute exists and has value
        has_embedding = getattr(obj, "embedding", None) is not None
        return cls(
            id=obj.id,
            page_id=obj.page_id,
            title=obj.title,
            description=obj.description,
            text_spans=obj.text_spans,
            bbox_x=obj.bbox_x,
            bbox_y=obj.bbox_y,
            bbox_width=obj.bbox_width,
            bbox_height=obj.bbox_height,
            png_path=obj.png_path,
            has_embedding=has_embedding,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )
