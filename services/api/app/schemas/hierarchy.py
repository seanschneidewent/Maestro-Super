"""Hierarchy response schemas for project visualization."""

from pydantic import BaseModel


class PointerSummary(BaseModel):
    """Minimal pointer info for hierarchy display."""

    id: str
    title: str


class PageInHierarchy(BaseModel):
    """Page with processing state and pointer count."""

    id: str
    pageName: str
    pageIndex: int = 0  # Zero-based index within multi-page PDF
    processedPass1: bool
    processedPass2: bool
    pointerCount: int
    pointers: list[PointerSummary]


class DisciplineInHierarchy(BaseModel):
    """Discipline with pages for hierarchy display."""

    id: str
    name: str
    displayName: str
    processed: bool
    pages: list[PageInHierarchy]


class ProjectHierarchyResponse(BaseModel):
    """Full project hierarchy for mind map visualization."""

    id: str
    name: str
    disciplines: list[DisciplineInHierarchy]
