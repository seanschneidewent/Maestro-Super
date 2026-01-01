"""Pointer reference schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PointerReferenceCreate(BaseModel):
    """Schema for creating a pointer reference."""

    source_pointer_id: str = Field(..., alias="sourcePointerId")
    target_page_id: str = Field(..., alias="targetPageId")
    justification: str = Field(..., min_length=1)

    model_config = ConfigDict(populate_by_name=True)


class PointerReferenceResponse(BaseModel):
    """Schema for pointer reference response."""

    id: str
    source_pointer_id: str = Field(alias="sourcePointerId")
    target_page_id: str = Field(alias="targetPageId")
    justification: str
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
