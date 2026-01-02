"""Search schemas."""

from pydantic import BaseModel, ConfigDict, Field


class SearchResult(BaseModel):
    """Single search result."""

    pointer_id: str = Field(alias="pointerId")
    title: str
    page_id: str = Field(alias="pageId")
    page_name: str = Field(alias="pageName")
    discipline: str
    relevance_snippet: str = Field(alias="relevanceSnippet")
    score: float

    model_config = ConfigDict(populate_by_name=True)


class SearchResponse(BaseModel):
    """Search response with results."""

    results: list[SearchResult]
    query: str
    count: int

    model_config = ConfigDict(populate_by_name=True)
