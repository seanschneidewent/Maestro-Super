"""Query agent tools for retrieving construction plan context."""

from typing import Callable

from sqlalchemy.orm import Session, joinedload

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
    PointerReferenceInTool,
    PointerSummary,
    ProjectPages,
)
from app.services.search import search_pointers  # Re-export existing search


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


async def list_project_pages(db: Session, project_id: str) -> ProjectPages | None:
    """
    Get full map of project with all disciplines and pages.

    Args:
        db: Database session
        project_id: Project UUID

    Returns:
        ProjectPages with all disciplines and pages, or None if not found
    """
    project = (
        db.query(Project)
        .options(joinedload(Project.disciplines).joinedload(Discipline.pages))
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
                "file_path": p.page.file_path if p.page else None,
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
    "get_pointer": get_pointer,
    "get_page_context": get_page_context,
    "get_discipline_overview": get_discipline_overview,
    "list_project_pages": list_project_pages,
    "get_references_to_page": get_references_to_page,
    "select_pointers": select_pointers,
}
