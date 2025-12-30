"""PageContext schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ProcessingStatus


class PageContextCreate(BaseModel):
    """Schema for creating a page context."""

    page_number: int = Field(..., ge=1, alias="pageNumber")
    sheet_number: str | None = Field(default=None, alias="sheetNumber")
    discipline_code: str | None = Field(default=None, alias="disciplineCode")

    model_config = ConfigDict(populate_by_name=True)


class PageContextUpdate(BaseModel):
    """Schema for updating a page context."""

    sheet_number: str | None = Field(default=None, alias="sheetNumber")
    discipline_code: str | None = Field(default=None, alias="disciplineCode")
    context_summary: str | None = Field(default=None, alias="contextSummary")
    pass1_output: dict[str, Any] | None = Field(default=None, alias="pass1Output")
    pass2_output: dict[str, Any] | None = Field(default=None, alias="pass2Output")
    inbound_references: dict[str, Any] | None = Field(
        default=None, alias="inboundReferences"
    )
    processing_status: ProcessingStatus | None = Field(
        default=None, alias="processingStatus"
    )
    retry_count: int | None = Field(default=None, alias="retryCount")

    model_config = ConfigDict(populate_by_name=True)


class PageContextResponse(BaseModel):
    """Schema for page context response."""

    id: str
    file_id: str = Field(alias="fileId")
    page_number: int = Field(alias="pageNumber")
    sheet_number: str | None = Field(default=None, alias="sheetNumber")
    discipline_code: str | None = Field(default=None, alias="disciplineCode")
    context_summary: str | None = Field(default=None, alias="contextSummary")
    pass1_output: dict[str, Any] | None = Field(default=None, alias="pass1Output")
    pass2_output: dict[str, Any] | None = Field(default=None, alias="pass2Output")
    inbound_references: dict[str, Any] | None = Field(
        default=None, alias="inboundReferences"
    )
    processing_status: ProcessingStatus = Field(alias="processingStatus")
    retry_count: int = Field(alias="retryCount")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
