"""Query agent tools for retrieving construction plan context."""

import logging
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy.orm import Session, joinedload

logger = logging.getLogger(__name__)

# Simple time-based cache for project structure
_project_structure_cache: dict[str, tuple[dict, datetime]] = {}
CACHE_TTL = timedelta(minutes=5)

from app.models.discipline import Discipline
from app.models.page import Page
from app.models.pointer import Pointer
from app.models.pointer_reference import PointerReference as PointerRefModel
from app.models.project import Project
from app.schemas.tools import (
    DisciplineOverview,
    DisciplinePages,
    DisciplineReference,
    InboundReference,
    PageContext,
    PageListItem,
    PageReferences,
    PageSummary,
    PointerDetail,
    PointerListItem,
    PointerReferenceInTool,
    PointerSummary,
    ProjectPages,
)
from app.services.search import search_pointers  # Re-export existing search


async def search_pages(
    db: Session,
    query: str,
    project_id: str,
    discipline: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """
    Search pages by name or context content.

    Args:
        db: Database session
        query: Search query (matches page_name, initial_context, full_context)
        project_id: Project UUID
        discipline: Optional discipline filter (e.g., "Electrical")
        limit: Max results (default 10)

    Returns:
        List of matching pages with id, name, discipline, and context snippet
    """
    from sqlalchemy import or_, func

    # Build base query
    base_query = (
        db.query(Page)
        .join(Page.discipline)
        .join(Discipline.project)
        .filter(Project.id == project_id)
    )

    # Add discipline filter if provided
    if discipline:
        base_query = base_query.filter(
            func.lower(Discipline.display_name).contains(discipline.lower())
        )

    # Search in page_name, initial_context, and full_context
    # Use word-level matching: all words must appear (but not as exact phrase)
    # This handles plural/singular mismatches like "plans" matching "PLAN"
    from sqlalchemy import and_

    # Strip common stop words that don't add search value
    STOP_WORDS = {"a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must", "shall", "can", "need", "dare", "ought", "used", "it", "its", "this", "that", "these", "those", "i", "you", "he", "she", "we", "they", "what", "which", "who", "whom", "where", "when", "why", "how", "all", "each", "every", "both", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just", "also"}

    words = [w for w in query.lower().split() if w not in STOP_WORDS]

    # If all words were stop words, fall back to original query
    if not words:
        words = query.lower().split()
    word_conditions = []

    for word in words:
        # Create pattern for this word
        word_pattern = f"%{word}%"

        # Also try without trailing 's' for plural handling
        # "plans" should match "PLAN", "floors" should match "FLOOR"
        if word.endswith('s') and len(word) > 2:
            singular_pattern = f"%{word[:-1]}%"
            word_condition = or_(
                Page.page_name.ilike(word_pattern),
                Page.page_name.ilike(singular_pattern),
                Page.initial_context.ilike(word_pattern),
                Page.initial_context.ilike(singular_pattern),
                Page.full_context.ilike(word_pattern),
                Page.full_context.ilike(singular_pattern),
            )
        else:
            word_condition = or_(
                Page.page_name.ilike(word_pattern),
                Page.initial_context.ilike(word_pattern),
                Page.full_context.ilike(word_pattern),
            )

        word_conditions.append(word_condition)

    # All words must match (AND) for more precise results
    if word_conditions:
        base_query = base_query.filter(and_(*word_conditions))

    pages = base_query.limit(limit).all()

    results = []
    for page in pages:
        # Find a relevant snippet from context
        context = page.full_context or page.initial_context or ""
        snippet = ""
        if context:
            # Try to find the query term and extract surrounding text
            lower_context = context.lower()
            lower_query = query.lower()
            idx = lower_context.find(lower_query)
            if idx >= 0:
                start = max(0, idx - 50)
                end = min(len(context), idx + len(query) + 100)
                snippet = ("..." if start > 0 else "") + context[start:end] + ("..." if end < len(context) else "")
            else:
                snippet = context[:150] + "..." if len(context) > 150 else context

        results.append({
            "page_id": str(page.id),
            "page_name": page.page_name,
            "discipline": page.discipline.display_name,
            "context_snippet": snippet,
        })

    return results


async def get_pointer(db: Session, pointer_id: str) -> PointerDetail | None:
    """
    Get full pointer data including references.

    Args:
        db: Database session
        pointer_id: Pointer UUID

    Returns:
        PointerDetail with references, or None if not found
    """
    pointer = (
        db.query(Pointer)
        .options(
            joinedload(Pointer.page).joinedload(Page.discipline),
            joinedload(Pointer.outbound_references).joinedload(PointerRefModel.target_page),
        )
        .filter(Pointer.id == pointer_id)
        .first()
    )

    if not pointer:
        return None

    return PointerDetail(
        pointer_id=str(pointer.id),
        title=pointer.title,
        page_id=str(pointer.page_id),
        page_name=pointer.page.page_name,
        description=pointer.description,
        text_spans=pointer.text_spans,
        references=[
            PointerReferenceInTool(
                target_page_id=str(ref.target_page_id),
                target_page_name=ref.target_page.page_name,
                justification=ref.justification,
            )
            for ref in pointer.outbound_references
        ],
        png_url=pointer.png_path,
    )


async def get_page_context(db: Session, page_id: str) -> PageContext | None:
    """
    Get page with all its pointers.

    Args:
        db: Database session
        page_id: Page UUID

    Returns:
        PageContext with pointers, or None if not found
    """
    page = (
        db.query(Page)
        .options(
            joinedload(Page.discipline),
            joinedload(Page.pointers).joinedload(Pointer.outbound_references),
        )
        .filter(Page.id == page_id)
        .first()
    )

    if not page:
        return None

    # Use full_context if available, fall back to initial_context
    summary = page.full_context or page.initial_context

    return PageContext(
        page_id=str(page.id),
        page_name=page.page_name,
        discipline=page.discipline.display_name,
        summary=summary,
        pointers=[
            PointerSummary(
                pointer_id=str(p.id),
                title=p.title,
                short_summary=(
                    p.description[:150] + "..."
                    if len(p.description) > 150
                    else p.description
                ),
                reference_count=len(p.outbound_references),
            )
            for p in page.pointers
        ],
    )


async def get_discipline_overview(
    db: Session, discipline_id: str
) -> DisciplineOverview | None:
    """
    Get high-level discipline view with pages and outbound reference stats.

    Args:
        db: Database session
        discipline_id: Discipline UUID

    Returns:
        DisciplineOverview with pages and reference counts, or None if not found
    """
    discipline = (
        db.query(Discipline)
        .options(
            joinedload(Discipline.pages)
            .joinedload(Page.pointers)
            .joinedload(Pointer.outbound_references)
            .joinedload(PointerRefModel.target_page)
            .joinedload(Page.discipline),
        )
        .filter(Discipline.id == discipline_id)
        .first()
    )

    if not discipline:
        return None

    # Count outbound references by target discipline
    ref_counts: dict[str, int] = {}
    for page in discipline.pages:
        for pointer in page.pointers:
            for ref in pointer.outbound_references:
                target_disc = ref.target_page.discipline.display_name
                ref_counts[target_disc] = ref_counts.get(target_disc, 0) + 1

    return DisciplineOverview(
        discipline_id=str(discipline.id),
        discipline=discipline.name,
        display_name=discipline.display_name,
        page_count=len(discipline.pages),
        pages=[
            PageSummary(
                page_id=str(p.id),
                page_name=p.page_name,
                pointer_count=len(p.pointers),
                summary_snippet=(
                    (p.full_context or p.initial_context or "")[:100] or None
                ),
            )
            for p in sorted(discipline.pages, key=lambda x: x.page_name)
        ],
        outbound_references=[
            DisciplineReference(target_discipline=disc, count=count)
            for disc, count in sorted(ref_counts.items(), key=lambda x: -x[1])
        ],
    )


async def _get_project_structure_impl(db: Session, project_id: str) -> dict | None:
    """
    Internal implementation - get lightweight project structure WITHOUT loading all pointers.

    This is optimized for the agent prefetch - returns discipline/page info
    without the expensive pointer data. Much faster than list_project_pages.
    """
    # Only load disciplines and pages - NO pointers
    disciplines = (
        db.query(Discipline)
        .options(joinedload(Discipline.pages))
        .filter(Discipline.project_id == project_id)
        .all()
    )

    if not disciplines:
        return None

    return {
        "disciplines": [
            {
                "discipline_id": str(d.id),
                "code": d.name,
                "name": d.display_name,
                "page_count": len(d.pages),
                "pages": [
                    {
                        "page_id": str(p.id),
                        "sheet_number": p.page_name,
                        "title": p.page_title,
                    }
                    for p in sorted(d.pages, key=lambda x: x.page_name)[:30]  # Limit to 30 pages per discipline
                ],
            }
            for d in sorted(disciplines, key=lambda x: x.display_name)
        ],
        "total_pages": sum(len(d.pages) for d in disciplines),
    }


async def get_project_structure_summary(db: Session, project_id: str) -> dict | None:
    """
    Get lightweight project structure with 5-minute caching.

    Args:
        db: Database session
        project_id: Project UUID

    Returns:
        Dict with disciplines and pages (no pointers), or None if not found
    """
    now = datetime.utcnow()

    # Check cache
    if project_id in _project_structure_cache:
        cached, cached_at = _project_structure_cache[project_id]
        if now - cached_at < CACHE_TTL:
            logger.debug(f"Cache hit for project structure: {project_id}")
            return cached

    # Cache miss - fetch from DB
    logger.debug(f"Cache miss for project structure: {project_id}")
    result = await _get_project_structure_impl(db, project_id)

    # Store in cache (even None results, to avoid repeated queries)
    if result is not None:
        _project_structure_cache[project_id] = (result, now)

    return result


def invalidate_project_structure_cache(project_id: str | None = None) -> None:
    """
    Invalidate the project structure cache.

    Args:
        project_id: If provided, only invalidate for this project. Otherwise, clear all.
    """
    if project_id:
        _project_structure_cache.pop(project_id, None)
    else:
        _project_structure_cache.clear()


async def list_project_pages(db: Session, project_id: str) -> ProjectPages | None:
    """
    Get full map of project with all disciplines, pages, and pointer titles.

    Args:
        db: Database session
        project_id: Project UUID

    Returns:
        ProjectPages with all disciplines, pages, and pointer titles, or None if not found
    """
    project = (
        db.query(Project)
        .options(
            joinedload(Project.disciplines)
            .joinedload(Discipline.pages)
            .joinedload(Page.pointers)
        )
        .filter(Project.id == project_id)
        .first()
    )

    if not project:
        return None

    return ProjectPages(
        project_id=str(project.id),
        disciplines=[
            DisciplinePages(
                name=d.name,
                display_name=d.display_name,
                pages=[
                    PageListItem(
                        page_id=str(p.id),
                        page_name=p.page_name,
                        pointers=[
                            PointerListItem(pointer_id=str(ptr.id), title=ptr.title)
                            for ptr in p.pointers
                        ] if p.pointers else None,
                    )
                    for p in sorted(d.pages, key=lambda x: x.page_name)
                ],
            )
            for d in sorted(project.disciplines, key=lambda x: x.display_name)
        ],
    )


async def get_references_to_page(db: Session, page_id: str) -> PageReferences | None:
    """
    Get all pointers that reference this page (reverse lookup).

    Args:
        db: Database session
        page_id: Page UUID

    Returns:
        PageReferences with all inbound references, or None if not found
    """
    page = (
        db.query(Page)
        .options(
            joinedload(Page.inbound_references)
            .joinedload(PointerRefModel.source_pointer)
            .joinedload(Pointer.page)
            .joinedload(Page.discipline),
        )
        .filter(Page.id == page_id)
        .first()
    )

    if not page:
        return None

    return PageReferences(
        page_id=str(page.id),
        page_name=page.page_name,
        referenced_by=[
            InboundReference(
                pointer_id=str(ref.source_pointer_id),
                pointer_title=ref.source_pointer.title,
                source_page_id=str(ref.source_pointer.page_id),
                source_page_name=ref.source_pointer.page.page_name,
                source_discipline=ref.source_pointer.page.discipline.display_name,
                justification=ref.justification,
            )
            for ref in page.inbound_references
        ],
        count=len(page.inbound_references),
    )


async def select_pages(db: Session, page_ids: list[str]) -> dict:
    """
    Return page details for display in the frontend viewer.

    Args:
        db: Database session
        page_ids: List of page UUIDs to display

    Returns:
        Dict with pages list containing page info for the viewer
    """
    pages = (
        db.query(Page)
        .options(joinedload(Page.discipline))
        .filter(Page.id.in_(page_ids))
        .all()
    )

    return {
        "pages": [
            {
                "page_id": str(p.id),
                "page_name": p.page_name,
                "file_path": p.page_image_path or p.file_path,  # Prefer PNG, fall back to PDF
                "discipline_id": str(p.discipline_id) if p.discipline_id else None,
                "discipline_name": p.discipline.display_name if p.discipline else None,
            }
            for p in pages
        ],
    }


async def select_pointers(db: Session, pointer_ids: list[str]) -> dict:
    """
    Return pointer details for highlighting in the frontend.

    Args:
        db: Database session
        pointer_ids: List of pointer UUIDs to highlight

    Returns:
        Dict with selected_pointer_ids and pointer details including bbox and page info
    """
    pointers = (
        db.query(Pointer)
        .options(joinedload(Pointer.page))
        .filter(Pointer.id.in_(pointer_ids))
        .all()
    )

    return {
        "selected_pointer_ids": pointer_ids,
        "pointers": [
            {
                "pointer_id": str(p.id),
                "title": p.title,
                "page_id": str(p.page_id),
                "page_name": p.page.page_name if p.page else None,
                "file_path": (p.page.page_image_path or p.page.file_path) if p.page else None,  # Prefer PNG
                "discipline_id": str(p.page.discipline_id) if p.page else None,
                "bbox_x": p.bbox_x,
                "bbox_y": p.bbox_y,
                "bbox_width": p.bbox_width,
                "bbox_height": p.bbox_height,
            }
            for p in pointers
        ],
    }


# Tool Registry - maps tool names to functions
# All tools take (db: Session, ...) as first argument and are async
TOOL_REGISTRY: dict[str, Callable] = {
    "search_pointers": search_pointers,
    "search_pages": search_pages,
    "get_pointer": get_pointer,
    "get_page_context": get_page_context,
    "get_discipline_overview": get_discipline_overview,
    "list_project_pages": list_project_pages,
    "get_project_structure_summary": get_project_structure_summary,
    "get_references_to_page": get_references_to_page,
    "select_pages": select_pages,
    "select_pointers": select_pointers,
}
