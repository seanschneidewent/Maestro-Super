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
from app.services.utils.sheet_cards import build_sheet_card
from app.services.utils.search import search_pointers  # Re-export existing search


async def search_pages(
    db: Session,
    query: str,
    project_id: str,
    discipline: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """
    Search pages by name or context content.

    Returns full page content for RAG - Gemini reads this to answer queries
    and identify which text to highlight.

    Args:
        db: Database session
        query: Search query (matches page_name, initial_context, full_context)
        project_id: Project UUID
        discipline: Optional discipline filter (e.g., "Electrical")
        limit: Max results (default 10)

    Returns:
        List of matching pages with id, name, discipline, full content,
        and compact Brain Mode metadata for smart selection.
    """
    from sqlalchemy import or_, func, and_

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

    # Search in page_name, initial_context, full_context, sheet_reflection, and context_markdown
    # Use word-level matching with plural handling.
    STOP_WORDS = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of",
        "with", "by", "is", "are", "was", "were", "be", "been", "being", "have",
        "has", "had", "do", "does", "did", "will", "would", "could", "should",
        "may", "might", "must", "shall", "can", "need", "dare", "ought", "used",
        "it", "its", "this", "that", "these", "those", "i", "you", "he", "she",
        "we", "they", "what", "which", "who", "whom", "where", "when", "why",
        "how", "all", "each", "every", "both", "few", "more", "most", "other",
        "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than",
        "too", "very", "just", "also",
    }

    SPEC_ANCHORS = {
        "schedule", "schedules", "spec", "specs", "specification", "specifications",
        "notes", "legend", "panel", "equipment", "wiring", "details",
    }

    def _tokenize(text: str) -> list[str]:
        tokens = [w for w in text.lower().split() if w and w not in STOP_WORDS]
        return tokens or [w for w in text.lower().split() if w]

    def _word_condition(word: str):
        word_pattern = f"%{word}%"
        if word.endswith("s") and len(word) > 2:
            singular_pattern = f"%{word[:-1]}%"
            return or_(
                Page.page_name.ilike(word_pattern),
                Page.page_name.ilike(singular_pattern),
                Page.initial_context.ilike(word_pattern),
                Page.initial_context.ilike(singular_pattern),
                Page.full_context.ilike(word_pattern),
                Page.full_context.ilike(singular_pattern),
                Page.sheet_reflection.ilike(word_pattern),
                Page.sheet_reflection.ilike(singular_pattern),
                Page.context_markdown.ilike(word_pattern),
                Page.context_markdown.ilike(singular_pattern),
            )
        return or_(
            Page.page_name.ilike(word_pattern),
            Page.initial_context.ilike(word_pattern),
            Page.full_context.ilike(word_pattern),
            Page.sheet_reflection.ilike(word_pattern),
            Page.context_markdown.ilike(word_pattern),
        )

    words = _tokenize(query)
    word_conditions = [_word_condition(word) for word in words]

    primary_limit = max(1, min(limit, max(3, int(limit * 0.6))))
    spec_limit_reserved = max(0, limit - primary_limit)

    primary_query = base_query
    if word_conditions:
        primary_query = primary_query.filter(and_(*word_conditions))

    primary_pages = primary_query.limit(primary_limit).all()

    # Secondary search: pull spec/schedule pages tied to the same query tokens.
    spec_pages = []
    if word_conditions:
        anchor_conditions = [_word_condition(anchor) for anchor in SPEC_ANCHORS]
        spec_tokens = [w for w in words if w not in SPEC_ANCHORS]
        token_conditions = [_word_condition(w) for w in (spec_tokens or words)]
        if anchor_conditions and token_conditions:
            primary_ids = {p.id for p in primary_pages}
            spec_limit = max(spec_limit_reserved, limit - len(primary_pages))
            spec_query = base_query.filter(or_(*anchor_conditions)).filter(or_(*token_conditions))
            if primary_ids:
                spec_query = spec_query.filter(~Page.id.in_(primary_ids))
            spec_pages = spec_query.limit(spec_limit).all()

    results = []
    # Preserve front-to-back feel: concept pages first, spec/schedule pages second.
    ordered_pages = (
        sorted(primary_pages, key=lambda p: p.page_name or "")
        + sorted(spec_pages, key=lambda p: p.page_name or "")
    )
    for page in ordered_pages:
        # Return full content for RAG - prefer sheet_reflection (Brain Mode)
        # Fall back to full_context or initial_context
        content = (
            page.sheet_reflection
            or page.context_markdown
            or page.full_context
            or page.initial_context
            or ""
        )

        keywords: list[str] = []
        master_index = page.master_index if isinstance(page.master_index, dict) else {}
        raw_keywords = master_index.get("keywords")
        if isinstance(raw_keywords, list):
            for keyword in raw_keywords:
                text = str(keyword).strip() if keyword is not None else ""
                if text:
                    keywords.append(text)
                if len(keywords) >= 10:
                    break

        questions_answered: list[str] = []
        if isinstance(page.questions_answered, list):
            for question in page.questions_answered:
                text = str(question).strip() if question is not None else ""
                if text:
                    questions_answered.append(text)
                if len(questions_answered) >= 3:
                    break

        compact_items: list[str] = []
        raw_items = master_index.get("items")
        if isinstance(raw_items, list):
            for item in raw_items:
                if isinstance(item, dict):
                    text = str(item.get("name") or "").strip()
                else:
                    text = str(item).strip() if item is not None else ""
                if text:
                    compact_items.append(text)
                if len(compact_items) >= 5:
                    break

        compact_master_index: dict | None = None
        if keywords or compact_items:
            compact_master_index = {}
            if keywords:
                compact_master_index["keywords"] = keywords
            if compact_items:
                compact_master_index["items"] = compact_items

        sheet_card = page.sheet_card if isinstance(page.sheet_card, dict) else None
        if not sheet_card:
            sheet_card = build_sheet_card(
                sheet_number=page.page_name,
                page_type=page.page_type,
                discipline_name=page.discipline.display_name if page.discipline else None,
                sheet_reflection=page.sheet_reflection,
                master_index=compact_master_index,
                keywords=keywords,
                cross_references=page.cross_references,
            )

        results.append({
            "page_id": str(page.id),
            "page_name": page.page_name,
            "discipline": page.discipline.display_name,
            "content": content,  # Full content for Gemini to read
            "sheet_reflection": page.sheet_reflection,
            "page_type": page.page_type,
            "cross_references": page.cross_references if isinstance(page.cross_references, list) else [],
            "keywords": keywords,
            "questions_answered": questions_answered,
            "master_index": compact_master_index,
            "sheet_card": sheet_card,
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

    # Prefer Agentic Vision summary while preserving legacy fallback behavior.
    summary = page.sheet_reflection or page.full_context or page.initial_context or page.context_markdown

    questions_answered = None
    if isinstance(page.questions_answered, list):
        questions_answered = [str(q) for q in page.questions_answered if q is not None]

    cross_references: list[str] | None = None
    if isinstance(page.cross_references, list):
        parsed_refs: list[str] = []
        for ref in page.cross_references:
            if isinstance(ref, str):
                sheet_name = ref.strip()
            elif isinstance(ref, dict):
                sheet_name = str(ref.get("sheet") or "").strip()
            else:
                sheet_name = ""
            if sheet_name:
                parsed_refs.append(sheet_name)
        cross_references = parsed_refs or None

    return PageContext(
        page_id=str(page.id),
        page_name=page.page_name,
        discipline=page.discipline.display_name if page.discipline else None,
        summary=summary,
        context_markdown=page.context_markdown,
        sheet_reflection=page.sheet_reflection,
        sheet_info=page.sheet_info if isinstance(page.sheet_info, dict) else None,
        questions_answered=questions_answered,
        cross_references=cross_references,
        region_count=len(page.regions) if isinstance(page.regions, list) else 0,
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
                        "title": None,  # Page model has no title field
                    }
                    for p in sorted(d.pages, key=lambda x: x.page_name)
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

    Includes semantic_index with OCR words and bboxes for text highlighting.

    Args:
        db: Database session
        page_ids: List of page UUIDs to display

    Returns:
        Dict with pages list containing page info and OCR data for highlighting
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
                # Include semantic_index for text highlighting
                "semantic_index": p.semantic_index,
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


def resolve_highlights(
    pages_data: list[dict],
    highlights: list[dict],
    query_tokens: list[str] | None = None,
) -> list[dict]:
    """
    Match text_matches from Gemini response to OCR words with bboxes.

    Args:
        pages_data: List of page dicts from select_pages (with semantic_index)
        highlights: List of highlight specs from Gemini [{page_id, text_matches}]
        query_tokens: Optional list of query tokens for relevance scoring

    Returns:
        List of resolved highlights with matched words and bboxes:
        [{
            page_id: str,
            words: [{id, text, bbox: {x0, y0, x1, y1, width, height}, role}]
        }]
    """
    # Build lookup: page_id -> semantic_index words + metadata
    page_words_lookup: dict[str, list[dict]] = {}
    page_meta_lookup: dict[str, dict] = {}
    for page in pages_data:
        page_id = page.get("page_id")
        semantic_index = page.get("semantic_index")
        if page_id and semantic_index:
            words = semantic_index.get("words", [])
            page_words_lookup[page_id] = words
            page_meta_lookup[page_id] = {
                "image_width": semantic_index.get("image_width"),
                "image_height": semantic_index.get("image_height"),
                "word_by_id": {w.get("id"): w for w in words if w.get("id") is not None},
            }

    def _normalize_compact(text: str) -> str:
        # Lowercase, drop all non-alphanumeric to normalize spacing/punctuation.
        return "".join(ch for ch in text.lower() if ch.isalnum())

    def _tokenize(text: str) -> list[str]:
        # Split on non-alphanumeric, keep meaningful tokens.
        tokens = []
        current = []
        for ch in text.lower():
            if ch.isalnum():
                current.append(ch)
            elif current:
                tokens.append("".join(current))
                current = []
        if current:
            tokens.append("".join(current))
        return [t for t in tokens if t]

    def _denormalize_bbox(bbox: list[float] | tuple, page_id: str) -> dict | None:
        if not bbox or len(bbox) != 4:
            return None
        meta = page_meta_lookup.get(page_id) or {}
        image_width = meta.get("image_width")
        image_height = meta.get("image_height")
        if not image_width or not image_height:
            return None

        x0, y0, x1, y1 = bbox
        # If coords are normalized (0-1), convert to pixels
        if 0 <= x0 <= 1 and 0 <= y0 <= 1 and 0 <= x1 <= 1 and 0 <= y1 <= 1:
            if x1 < x0 or y1 < y0:
                # Treat as x,y,w,h in normalized space
                x1 = x0 + x1
                y1 = y0 + y1
            x0_px = x0 * image_width
            y0_px = y0 * image_height
            x1_px = x1 * image_width
            y1_px = y1 * image_height
        else:
            # Assume already in pixel space
            x0_px, y0_px, x1_px, y1_px = x0, y0, x1, y1

        width = max(0, x1_px - x0_px)
        height = max(0, y1_px - y0_px)
        return {
            "x0": x0_px,
            "y0": y0_px,
            "x1": x1_px,
            "y1": y1_px,
            "width": width,
            "height": height,
        }

    def _merge_adjacent_words(words: list[dict]) -> list[dict]:
        if len(words) <= 1:
            return words

        def _overlap_y(a: dict, b: dict) -> bool:
            ay0, ay1 = a["bbox"]["y0"], a["bbox"]["y1"]
            by0, by1 = b["bbox"]["y0"], b["bbox"]["y1"]
            overlap = min(ay1, by1) - max(ay0, by0)
            return overlap >= min(a["bbox"]["height"], b["bbox"]["height"]) * 0.5

        def _gap_x(a: dict, b: dict) -> float:
            return b["bbox"]["x0"] - a["bbox"]["x1"]

        words_sorted = sorted(words, key=lambda w: (w["bbox"]["y0"], w["bbox"]["x0"]))
        merged: list[dict] = []

        for word in words_sorted:
            if not merged:
                merged.append(word)
                continue

            last = merged[-1]
            same_source = (word.get("source") == last.get("source"))
            same_line = _overlap_y(last, word)
            avg_height = (last["bbox"]["height"] + word["bbox"]["height"]) / 2
            gap_thresh = max(4, avg_height * 0.4)
            close_enough = _gap_x(last, word) <= gap_thresh

            if same_source and same_line and close_enough:
                # Merge into last
                last_bbox = last["bbox"]
                word_bbox = word["bbox"]
                last_bbox["x0"] = min(last_bbox["x0"], word_bbox["x0"])
                last_bbox["y0"] = min(last_bbox["y0"], word_bbox["y0"])
                last_bbox["x1"] = max(last_bbox["x1"], word_bbox["x1"])
                last_bbox["y1"] = max(last_bbox["y1"], word_bbox["y1"])
                last_bbox["width"] = last_bbox["x1"] - last_bbox["x0"]
                last_bbox["height"] = last_bbox["y1"] - last_bbox["y0"]
                last["text"] = f"{last.get('text', '').strip()} {word.get('text', '').strip()}".strip()
                # Keep the most confident label if present
                if not last.get("confidence") and word.get("confidence"):
                    last["confidence"] = word.get("confidence")
            else:
                merged.append(word)

        return merged

    resolved = []
    for highlight in highlights:
        page_id = highlight.get("page_id")
        text_matches = highlight.get("text_matches", [])
        semantic_refs = highlight.get("semantic_refs") or []
        bboxes = list(highlight.get("bboxes") or [])
        bbox_single = highlight.get("bbox")
        source = highlight.get("source")

        if not page_id:
            continue

        ocr_words = page_words_lookup.get(page_id, [])
        if not ocr_words:
            logger.warning(f"No OCR words found for page {page_id}")
            continue

        matched_words: list[dict] = []

        # If semantic_refs or bbox provided, resolve those directly (agentic vision path)
        if semantic_refs or bboxes or bbox_single:
            meta = page_meta_lookup.get(page_id) or {}
            word_by_id = meta.get("word_by_id") or {}
            if semantic_refs:
                for ref in semantic_refs:
                    ref_id = ref
                    try:
                        ref_id = int(ref)
                    except Exception:
                        pass
                    word = word_by_id.get(ref_id)
                    if not word:
                        continue
                    matched_words.append({
                        "id": word.get("id"),
                        "text": word.get("text"),
                        "bbox": word.get("bbox"),
                        "role": word.get("role"),
                        "region_type": word.get("region_type"),
                        "source": source or "agent",
                    })

            if bbox_single:
                bboxes.append({"bbox": bbox_single})

            for bbox_item in bboxes:
                bbox = bbox_item.get("bbox") if isinstance(bbox_item, dict) else bbox_item
                resolved_bbox = _denormalize_bbox(bbox, page_id)
                if not resolved_bbox:
                    continue
                matched_words.append({
                    "id": None,
                    "text": bbox_item.get("source_text") if isinstance(bbox_item, dict) else "",
                    "bbox": resolved_bbox,
                    "role": bbox_item.get("category") if isinstance(bbox_item, dict) else None,
                    "region_type": None,
                    "source": source or "agent",
                    "confidence": bbox_item.get("confidence") if isinstance(bbox_item, dict) else None,
                })

            if matched_words:
                merged_words = _merge_adjacent_words(matched_words)
                resolved.append({
                    "page_id": page_id,
                    "words": merged_words,
                })
            continue

        if not text_matches:
            continue

        matched_word_ids: set[int] = set()  # Track by ID to avoid duplicates
        matched_word_keys: set[str] = set()  # Fallback for words without IDs (text+bbox)

        # Precompute normalized OCR word representations
        ocr_word_texts = [w.get("text", "") for w in ocr_words]
        ocr_word_compact = [_normalize_compact(t) for t in ocr_word_texts]

        def _track_word(word: dict) -> bool:
            word_id = word.get("id")
            if word_id is not None:
                if word_id in matched_word_ids:
                    return False
                matched_word_ids.add(word_id)
            else:
                bbox = word.get("bbox", {})
                word_key = f"{word.get('text')}:{bbox.get('x0')}:{bbox.get('y0')}"
                if word_key in matched_word_keys:
                    return False
                matched_word_keys.add(word_key)
            matched_words.append({
                "id": word_id,
                "text": word.get("text"),
                "bbox": word.get("bbox"),
                "role": word.get("role"),
                "region_type": word.get("region_type"),
            })
            return True

        for text_match in text_matches:
            if not text_match:
                continue

            # Ensure text_match is a string (Gemini might return numbers)
            if not isinstance(text_match, str):
                text_match = str(text_match)

            match_lower = text_match.lower().strip()
            match_compact = _normalize_compact(text_match)
            match_tokens = _tokenize(text_match)

            # Skip empty strings after stripping (would match everything)
            if not match_lower or not match_compact:
                continue

            # 1) Single-word matching with normalized compact strings
            for idx, word in enumerate(ocr_words):
                word_text = ocr_word_texts[idx].lower().strip()
                if not word_text:
                    continue
                word_compact = ocr_word_compact[idx]
                if not word_compact:
                    continue

                if (
                    match_lower in word_text
                    or word_text in match_lower
                    or match_compact in word_compact
                    or word_compact in match_compact
                ):
                    _track_word(word)

            # 2) Phrase matching across adjacent words (handles "WALK IN COOLER", "3' - 6"")
            max_window = 20  # prevent runaway scans on long pages
            n = len(ocr_words)
            for start in range(n):
                concat = ""
                end_limit = min(start + max_window, n)
                for end in range(start, end_limit):
                    concat += ocr_word_compact[end]
                    if not concat:
                        continue
                    if match_compact in concat:
                        for i in range(start, end + 1):
                            _track_word(ocr_words[i])
                        break
                    if len(concat) > len(match_compact) * 2:
                        break

            # 3) Token fallback: match significant tokens to OCR words
            if len(match_tokens) > 1:
                for idx, word in enumerate(ocr_words):
                    word_compact = ocr_word_compact[idx]
                    if not word_compact:
                        continue
                    for token in match_tokens:
                        if len(token) >= 3 and token in word_compact:
                            _track_word(word)
                            break

        if matched_words:
            # Tag fuzzy matches as search-based highlights
            for word in matched_words:
                word.setdefault("source", "search")
            merged_words = _merge_adjacent_words(matched_words)
            resolved.append({
                "page_id": page_id,
                "words": merged_words,
            })

    return resolved


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
