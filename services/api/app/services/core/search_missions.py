"""
Search Mission Builder for Deep Mode V3.

Takes Fast Mode output + Brain Mode context and builds
structured per-page search prompts for Agentic Vision.

Instead of pre-selecting regions and constraining the model,
we build a search mission that tells the model WHAT to look for
on each page, with context about WHY this page was selected.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def build_search_missions(
    query: str,
    ordered_page_ids: list[str],
    page_map: dict[str, Any],
    region_matches: dict[str, list[dict[str, Any]]],
    fast_mode_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build structured search missions for Deep Mode Agentic Vision.

    Args:
        query: User's original query
        ordered_page_ids: Pages selected by Fast Mode, in relevance order
        page_map: Mapping of page_id -> Page ORM objects with Brain Mode data
        region_matches: RAG search results (regions matched per page)
        fast_mode_context: Optional Fast Mode output (selected_pages with relevance)

    Returns:
        {
            "query": "...",
            "pages": [
                {
                    "page_id": "...",
                    "page_name": "...",
                    "discipline": "...",
                    "page_type": "...",
                    "search_targets": ["...", "..."],
                    "context": "...",
                    "sheet_reflection": "..."
                }
            ]
        }
    """
    # Extract relevance reasons from Fast Mode if available
    fast_relevance: dict[str, str] = {}
    if isinstance(fast_mode_context, dict):
        selected_pages = fast_mode_context.get("selected_pages") or []
        for sp in selected_pages:
            if isinstance(sp, dict):
                pid = str(sp.get("page_id") or "").strip()
                rel = str(sp.get("relevance") or "").strip()
                if pid and rel:
                    fast_relevance[pid] = rel

    pages_payload: list[dict[str, Any]] = []

    for page_id in ordered_page_ids:
        page = page_map.get(page_id)
        if not page:
            continue

        page_name = str(getattr(page, "page_name", "") or "")
        page_type = str(getattr(page, "page_type", "") or "")
        discipline_obj = getattr(page, "discipline", None)
        discipline = (
            str(getattr(discipline_obj, "display_name", "") or "")
            if discipline_obj
            else ""
        )

        # Get Brain Mode context
        sheet_reflection = str(
            getattr(page, "sheet_reflection", "")
            or getattr(page, "context_markdown", "")
            or getattr(page, "full_context", "")
            or getattr(page, "initial_context", "")
            or ""
        )

        # Get regions for context (not constraints)
        raw_regions = (
            page.regions if isinstance(getattr(page, "regions", None), list) else []
        )
        region_summaries = _summarize_regions(raw_regions)

        # Get cross-references
        cross_refs = _extract_cross_refs(page)

        # Get master index keywords
        master_index = getattr(page, "master_index", None)
        keywords = _extract_keywords(master_index)

        # Get RAG-matched regions for this page
        matched_regions = region_matches.get(str(page_id)) or []
        rag_hints = _extract_rag_hints(matched_regions)

        # Fast Mode relevance reason
        relevance = fast_relevance.get(str(page_id), "")

        # Build search targets
        search_targets = _build_search_targets(
            query=query,
            page_name=page_name,
            page_type=page_type,
            discipline=discipline,
            rag_hints=rag_hints,
            keywords=keywords,
            relevance=relevance,
        )

        # Build context string
        context = _build_page_context(
            page_type=page_type,
            discipline=discipline,
            region_summaries=region_summaries,
            cross_refs=cross_refs,
            relevance=relevance,
        )

        pages_payload.append(
            {
                "page_id": str(page_id),
                "page_name": page_name,
                "discipline": discipline,
                "page_type": page_type,
                "search_targets": search_targets,
                "context": context,
                "sheet_reflection": (
                    sheet_reflection[:500] if sheet_reflection else ""
                ),
            }
        )

    return {
        "query": query,
        "pages": pages_payload,
    }


def _summarize_regions(regions: list[dict[str, Any]]) -> list[str]:
    """Compact summaries of Brain Mode regions (for context, not constraint)."""
    summaries: list[str] = []
    for region in regions[:10]:
        if not isinstance(region, dict):
            continue
        region_type = str(region.get("type") or "").strip()
        label = str(region.get("label") or "").strip()
        if label:
            summaries.append(f"{region_type}: {label}" if region_type else label)
        elif region_type:
            summaries.append(region_type)
    return summaries


def _extract_cross_refs(page: Any) -> list[str]:
    """Extract cross-reference sheet names from a Page object."""
    cross_refs_raw = getattr(page, "cross_references", None)
    if not isinstance(cross_refs_raw, list):
        return []
    refs: list[str] = []
    for ref in cross_refs_raw:
        if isinstance(ref, str) and ref.strip():
            refs.append(ref.strip())
        elif isinstance(ref, dict):
            sheet = ref.get("sheet") or ref.get("target_page") or ""
            if str(sheet).strip():
                refs.append(str(sheet).strip())
    return refs[:8]


def _extract_keywords(master_index: Any) -> list[str]:
    """Extract keywords from master index."""
    if not isinstance(master_index, dict):
        return []
    keywords = master_index.get("keywords") or []
    if not isinstance(keywords, list):
        return []
    return [str(k).strip() for k in keywords[:12] if str(k).strip()]


def _extract_rag_hints(matched_regions: list[dict[str, Any]]) -> list[str]:
    """Extract why RAG matched this page (region labels/types that scored)."""
    hints: list[str] = []
    for region in matched_regions[:5]:
        if not isinstance(region, dict):
            continue
        label = str(region.get("label") or "").strip()
        region_type = str(
            region.get("type") or region.get("region_type") or ""
        ).strip()
        if label:
            hints.append(label)
        elif region_type:
            hints.append(region_type)
    return hints


def _build_search_targets(
    *,
    query: str,
    page_name: str,
    page_type: str,
    discipline: str,
    rag_hints: list[str],
    keywords: list[str],
    relevance: str,
) -> list[str]:
    """
    Build 2-4 specific search targets for a page.

    These tell the Agentic Vision model WHAT to look for on this page,
    grounded in the query + why this page was selected.
    """
    targets: list[str] = []

    # Primary: what the user is looking for on THIS type of page
    if page_type == "schedule":
        targets.append(f"Find any row or entry related to: {query}")
        if rag_hints:
            targets.append(f"Check these areas: {', '.join(rag_hints[:3])}")
    elif page_type in ("floor_plan", "plan"):
        targets.append(f"Locate on the floor plan: {query}")
        targets.append(
            "Read any equipment tags, labels, or grid references near the target"
        )
    elif page_type == "detail_sheet":
        targets.append(f"Find details related to: {query}")
        targets.append("Read dimensions, notes, and callouts in the detail")
    elif page_type in ("notes", "spec"):
        targets.append(f"Find any notes or specifications about: {query}")
    elif page_type in ("section", "elevation"):
        targets.append(f"Find sections or elevations showing: {query}")
        targets.append("Read any dimensions, heights, or clearances")
    else:
        targets.append(f"Search for information about: {query}")

    # Secondary: if Fast Mode gave a relevance reason, use it
    if relevance and len(targets) < 4:
        targets.append(f"Specifically: {relevance}")

    # Tertiary: if RAG matched specific regions, hint at them
    if rag_hints and len(targets) < 4:
        targets.append(
            f"RAG matched these areas: {', '.join(rag_hints[:3])}"
        )

    return targets[:4]


def _build_page_context(
    *,
    page_type: str,
    discipline: str,
    region_summaries: list[str],
    cross_refs: list[str],
    relevance: str,
) -> str:
    """Build a concise context string about the page."""
    parts: list[str] = []

    if discipline and page_type:
        parts.append(f"{discipline} {page_type}.")
    elif page_type:
        parts.append(f"Page type: {page_type}.")

    if region_summaries:
        parts.append(f"Known areas: {', '.join(region_summaries[:5])}.")

    if cross_refs:
        parts.append(f"Cross-references: {', '.join(cross_refs[:4])}.")

    if relevance:
        parts.append(f"Selected because: {relevance}")

    return " ".join(parts)
