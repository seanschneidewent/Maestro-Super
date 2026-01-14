"""Schemas for query agent tools."""

from pydantic import BaseModel, ConfigDict, Field


# Tool 2: get_pointer
class PointerReferenceInTool(BaseModel):
    """A reference from a pointer to another page."""

    target_page_id: str = Field(alias="targetPageId")
    target_page_name: str = Field(alias="targetPageName")
    justification: str

    model_config = ConfigDict(populate_by_name=True)


class PointerDetail(BaseModel):
    """Full pointer data including references."""

    pointer_id: str = Field(alias="pointerId")
    title: str
    page_id: str = Field(alias="pageId")
    page_name: str = Field(alias="pageName")
    description: str
    text_spans: list[str] | None = Field(alias="textSpans", default=None)
    references: list[PointerReferenceInTool]
    png_url: str | None = Field(alias="pngUrl", default=None)

    model_config = ConfigDict(populate_by_name=True)


# Tool 3: get_page_context
class PointerSummary(BaseModel):
    """Summary of a pointer within a page."""

    pointer_id: str = Field(alias="pointerId")
    title: str
    short_summary: str = Field(alias="shortSummary")
    reference_count: int = Field(alias="referenceCount")

    model_config = ConfigDict(populate_by_name=True)


class PageContext(BaseModel):
    """Page with all its pointers."""

    page_id: str = Field(alias="pageId")
    page_name: str = Field(alias="pageName")
    discipline: str
    summary: str | None
    pointers: list[PointerSummary]

    model_config = ConfigDict(populate_by_name=True)


# Tool 4: get_discipline_overview
class PageSummary(BaseModel):
    """Summary of a page within a discipline."""

    page_id: str = Field(alias="pageId")
    page_name: str = Field(alias="pageName")
    pointer_count: int = Field(alias="pointerCount")
    summary_snippet: str | None = Field(alias="summarySnippet", default=None)

    model_config = ConfigDict(populate_by_name=True)


class DisciplineReference(BaseModel):
    """Count of references to another discipline."""

    target_discipline: str = Field(alias="targetDiscipline")
    count: int

    model_config = ConfigDict(populate_by_name=True)


class DisciplineOverview(BaseModel):
    """High-level discipline view with pages and reference stats."""

    discipline_id: str = Field(alias="disciplineId")
    discipline: str
    display_name: str = Field(alias="displayName")
    page_count: int = Field(alias="pageCount")
    pages: list[PageSummary]
    outbound_references: list[DisciplineReference] = Field(alias="outboundReferences")

    model_config = ConfigDict(populate_by_name=True)


# Tool 5: list_project_pages
class PageListItem(BaseModel):
    """Minimal page info for listing."""

    page_id: str = Field(alias="pageId")
    page_name: str = Field(alias="pageName")
    pointer_count: int = Field(alias="pointerCount", default=0)

    model_config = ConfigDict(populate_by_name=True)


class DisciplinePages(BaseModel):
    """Discipline with its pages."""

    name: str
    display_name: str = Field(alias="displayName")
    pages: list[PageListItem]

    model_config = ConfigDict(populate_by_name=True)


class ProjectPages(BaseModel):
    """Full map of project with all disciplines and pages."""

    project_id: str = Field(alias="projectId")
    disciplines: list[DisciplinePages]

    model_config = ConfigDict(populate_by_name=True)


# Tool 6: get_references_to_page
class InboundReference(BaseModel):
    """A pointer that references a page."""

    pointer_id: str = Field(alias="pointerId")
    pointer_title: str = Field(alias="pointerTitle")
    source_page_id: str = Field(alias="sourcePageId")
    source_page_name: str = Field(alias="sourcePageName")
    source_discipline: str = Field(alias="sourceDiscipline")
    justification: str

    model_config = ConfigDict(populate_by_name=True)


class PageReferences(BaseModel):
    """All pointers that reference a page (reverse lookup)."""

    page_id: str = Field(alias="pageId")
    page_name: str = Field(alias="pageName")
    referenced_by: list[InboundReference] = Field(alias="referencedBy")
    count: int

    model_config = ConfigDict(populate_by_name=True)
