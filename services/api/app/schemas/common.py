"""Common schemas shared across modules."""

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Bounds(BaseModel):
    """
    Normalized coordinates (0-1 space).

    Matches frontend interface: { xNorm, yNorm, wNorm, hNorm }
    """

    x_norm: float = Field(..., ge=0, le=1, alias="xNorm")
    y_norm: float = Field(..., ge=0, le=1, alias="yNorm")
    w_norm: float = Field(..., ge=0, le=1, alias="wNorm")
    h_norm: float = Field(..., ge=0, le=1, alias="hNorm")

    model_config = ConfigDict(populate_by_name=True)


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response wrapper."""

    items: list[T]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")

    model_config = ConfigDict(populate_by_name=True)


class TimestampMixin(BaseModel):
    """Mixin for models with timestamps."""

    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)
