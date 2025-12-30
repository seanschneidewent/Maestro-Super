"""ContextPointer schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PointerStatus
from app.schemas.common import Bounds


class AIAnalysis(BaseModel):
    """AI analysis output from Gemini."""

    technical_description: str | None = Field(default=None, alias="technicalDescription")
    trade_category: str | None = Field(default=None, alias="tradeCategory")
    elements: list[dict[str, Any]] | None = None
    measurements: list[dict[str, Any]] | None = None
    recommendations: str | None = None
    issues: list[dict[str, Any]] | None = None

    model_config = ConfigDict(populate_by_name=True)


class ContextPointerCreate(BaseModel):
    """Schema for creating a context pointer."""

    page_number: int = Field(..., ge=1, alias="pageNumber")
    bounds: Bounds
    title: str | None = None
    description: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class ContextPointerUpdate(BaseModel):
    """Schema for updating a context pointer."""

    title: str | None = None
    description: str | None = None
    status: PointerStatus | None = None
    snapshot_url: str | None = Field(default=None, alias="snapshotUrl")

    # AI fields (set by processing pipeline)
    ai_technical_description: str | None = Field(
        default=None, alias="aiTechnicalDescription"
    )
    ai_trade_category: str | None = Field(default=None, alias="aiTradeCategory")
    ai_elements: list[dict[str, Any]] | None = Field(default=None, alias="aiElements")
    ai_measurements: list[dict[str, Any]] | None = Field(
        default=None, alias="aiMeasurements"
    )
    ai_recommendations: str | None = Field(default=None, alias="aiRecommendations")
    ai_issues: list[dict[str, Any]] | None = Field(default=None, alias="aiIssues")
    text_content: dict[str, Any] | None = Field(default=None, alias="textContent")

    model_config = ConfigDict(populate_by_name=True)


class ContextPointerResponse(BaseModel):
    """
    Schema for context pointer response.

    Matches frontend ContextPointer interface.
    """

    id: str
    file_id: str = Field(alias="fileId")
    page_number: int = Field(alias="pageNumber")
    bounds: Bounds
    title: str | None = None
    description: str | None = None
    status: PointerStatus
    snapshot_url: str | None = Field(default=None, alias="snapshotUrl")
    ai_analysis: AIAnalysis | None = Field(default=None, alias="aiAnalysis")
    committed_at: datetime | None = Field(default=None, alias="committedAt")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @classmethod
    def from_orm(cls, pointer: Any) -> "ContextPointerResponse":
        """Convert ORM model to response schema."""
        # Build AI analysis if any fields present
        ai_analysis = None
        if any(
            [
                pointer.ai_technical_description,
                pointer.ai_trade_category,
                pointer.ai_elements,
                pointer.ai_measurements,
                pointer.ai_recommendations,
                pointer.ai_issues,
            ]
        ):
            ai_analysis = AIAnalysis(
                technical_description=pointer.ai_technical_description,
                trade_category=pointer.ai_trade_category,
                elements=pointer.ai_elements,
                measurements=pointer.ai_measurements,
                recommendations=pointer.ai_recommendations,
                issues=pointer.ai_issues,
            )

        return cls(
            id=pointer.id,
            file_id=pointer.file_id,
            page_number=pointer.page_number,
            bounds=Bounds(
                x_norm=pointer.x_norm,
                y_norm=pointer.y_norm,
                w_norm=pointer.w_norm,
                h_norm=pointer.h_norm,
            ),
            title=pointer.title,
            description=pointer.description,
            status=pointer.status,
            snapshot_url=pointer.snapshot_url,
            ai_analysis=ai_analysis,
            committed_at=pointer.committed_at,
            created_at=pointer.created_at,
        )
