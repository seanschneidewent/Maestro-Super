"""Query agent for navigating construction plan graph.

Fast mode routes users to likely pages using RAG + project structure context.
Med mode adds deterministic region highlighting from precomputed Brain Mode metadata.
Deep mode adds streamed Gemini agentic vision exploration on top of the same RAG seed.
Grok via OpenRouter remains available for legacy fast-mode behavior.
"""

import asyncio
import json
import logging
import os
import re
from typing import Any, AsyncIterator, Literal

import openai
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.models.discipline import Discipline
from app.models.page import Page
from app.services.utils.sheet_cards import build_sheet_card

logger = logging.getLogger(__name__)

FAST_PAGE_LIMIT = 8
DEEP_PAGE_LIMIT = 5
CROSS_REF_PAGE_LIMIT = 3
DEEP_CANDIDATE_REGION_LIMIT = 8
DEEP_EXPANSION_REGION_LIMIT = 4
DEEP_MICRO_CROP_LIMIT = 12
DEEP_MAX_FINDINGS = 12
MED_PAGE_LIMIT = 4
MED_TOTAL_HIGHLIGHT_LIMIT = 8
MED_HIGHLIGHTS_PER_PAGE = 3
PAGE_NAVIGATION_TERMS = {
    "page", "pages", "sheet", "sheets", "plan", "plans", "drawing", "drawings",
}
PAGE_NAVIGATION_STOP_TOKENS = {
    "page", "pages", "sheet", "sheets", "plan", "plans", "drawing", "drawings", "floor",
}
ROUTER_PAGE_TYPE_ALIASES = {
    "floor_plan": {"floor_plan", "plan"},
    "plan": {"plan", "floor_plan"},
    "detail_sheet": {"detail_sheet", "detail"},
    "detail": {"detail_sheet", "detail"},
    "schedule": {"schedule"},
    "spec": {"spec", "specification"},
    "notes": {"notes", "note"},
    "rcp": {"rcp"},
    "demo": {"demo", "demolition"},
    "section": {"section"},
    "elevation": {"elevation"},
    "cover": {"cover"},
}
DISCIPLINE_QUERY_HINTS: dict[str, set[str]] = {
    "architectural": {"architectural", "arch", "life safety", "egress"},
    "mechanical": {"mechanical", "hvac", "duct", "rtu", "ahu", "mech"},
    "electrical": {"electrical", "panel", "circuit", "one line", "lighting", "power"},
    "plumbing": {"plumbing", "fixture", "sanitary", "water", "valve"},
    "kitchen": {"kitchen", "food service", "hood", "walk in cooler", "wic"},
    "structural": {"structural", "beam", "column", "foundation"},
}
GENERIC_SHEET_TOKENS = {
    "cover",
    "sheet index",
    "sheet list",
    "general notes",
    "legend",
}


def _build_history_context(history_messages: list[dict[str, Any]] | None) -> str:
    if not history_messages:
        return ""
    history_parts = []
    for msg in history_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if content:
            history_parts.append(f"{role.upper()}: {content}")
    return "\n".join(history_parts)


def _build_viewing_context_str(viewing_context: dict[str, Any] | None) -> str:
    if not viewing_context:
        return ""
    page_name = viewing_context.get("page_name", "unknown page")
    discipline = viewing_context.get("discipline_name")
    if discipline:
        return f"User is viewing page {page_name} from {discipline}"
    return f"User is viewing page {page_name}"


def _page_sort_key(page_name: str) -> list:
    if not page_name:
        return []
    parts = re.split(r"(\d+)", page_name)
    key: list = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part.lower())
    return key


def _extract_query_tokens(query: str) -> list[str]:
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
    tokens = [w for w in query.lower().split() if w and w not in STOP_WORDS]
    return tokens or [w for w in query.lower().split() if w]


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())).strip()


def _normalize_router_terms(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = _normalize_text(str(value or ""))
        if not term:
            continue
        if term in PAGE_NAVIGATION_STOP_TOKENS:
            continue
        if term in seen:
            continue
        seen.add(term)
        result.append(term)
        if len(result) >= 4:
            break
    return result


def _normalize_router_page_types(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        page_type = _normalize_text(str(value or "")).replace(" ", "_")
        if not page_type:
            continue
        if page_type in seen:
            continue
        seen.add(page_type)
        result.append(page_type)
        if len(result) >= 3:
            break
    return result


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return default


def _normalize_page_type(page_type: str) -> str:
    normalized = _normalize_text(page_type).replace(" ", "_")
    if normalized in ROUTER_PAGE_TYPE_ALIASES:
        return normalized
    if normalized == "detail":
        return "detail_sheet"
    if normalized == "specification":
        return "spec"
    if normalized == "note":
        return "notes"
    return normalized


def _page_matches_router_constraints(
    page: dict[str, Any],
    must_terms: list[str],
    preferred_page_types: list[str],
) -> bool:
    if not isinstance(page, dict):
        return False

    parts: list[str] = [
        str(page.get("page_name") or ""),
        str(page.get("discipline") or ""),
        str(page.get("page_type") or ""),
    ]

    keywords = page.get("keywords")
    if isinstance(keywords, list):
        parts.extend(str(value or "") for value in keywords)

    questions = page.get("questions_answered")
    if isinstance(questions, list):
        parts.extend(str(value or "") for value in questions)

    master_index = page.get("master_index")
    if isinstance(master_index, dict):
        master_keywords = master_index.get("keywords")
        if isinstance(master_keywords, list):
            parts.extend(str(value or "") for value in master_keywords)
        master_items = master_index.get("items")
        if isinstance(master_items, list):
            parts.extend(str(value or "") for value in master_items)

    content = str(page.get("content") or "")
    if content:
        parts.append(content[:700])

    haystack = _normalize_text(" ".join(parts))
    if must_terms and any(term not in haystack for term in must_terms):
        return False

    if preferred_page_types:
        page_type = _normalize_page_type(str(page.get("page_type") or ""))
        if page_type:
            preferred_match = False
            for preferred in preferred_page_types:
                aliases = ROUTER_PAGE_TYPE_ALIASES.get(preferred, {preferred})
                if page_type in aliases:
                    preferred_match = True
                    break
            if not preferred_match:
                return False
        else:
            # If page_type metadata is missing, match on textual hints.
            page_text = _normalize_text(
                " ".join(
                    [
                        str(page.get("page_name") or ""),
                        content[:700],
                    ]
                )
            )
            if not any(
                _normalize_text(preferred.replace("_", " ")) in page_text
                for preferred in preferred_page_types
            ):
                return False

    return True


def _filter_pages_for_router(
    pages: list[dict[str, Any]],
    must_terms: list[str],
    preferred_page_types: list[str],
) -> list[dict[str, Any]]:
    return [
        page
        for page in pages
        if _page_matches_router_constraints(page, must_terms, preferred_page_types)
    ]


def _build_routed_search_query(query: str, must_terms: list[str], preferred_page_types: list[str]) -> str:
    extras: list[str] = []
    for term in must_terms:
        if term:
            extras.append(term)
    for page_type in preferred_page_types:
        if page_type:
            extras.append(page_type.replace("_", " "))

    if not extras:
        return query

    merged = [query]
    seen: set[str] = {_normalize_text(query)}
    for extra in extras:
        key = _normalize_text(extra)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(extra)
    return " ".join(merged)


def _is_page_navigation_query(query: str) -> bool:
    query_tokens = _extract_query_tokens(query)
    if any(token in PAGE_NAVIGATION_TERMS for token in query_tokens):
        return True

    query_lower = query.lower()
    if "floor plan" in query_lower or "sheet list" in query_lower:
        return True
    return False


def _select_project_tree_page_ids(
    project_structure: dict[str, Any] | None,
    query: str,
    limit: int,
) -> list[str]:
    if not isinstance(project_structure, dict):
        return []

    disciplines = project_structure.get("disciplines")
    if not isinstance(disciplines, list):
        return []

    raw_tokens = _extract_query_tokens(query)
    query_tokens = [token for token in raw_tokens if token not in PAGE_NAVIGATION_STOP_TOKENS]

    scored_entries: list[tuple[int, str, str]] = []
    fallback_page_ids: list[str] = []

    for discipline in disciplines:
        if not isinstance(discipline, dict):
            continue

        discipline_name = str(
            discipline.get("name")
            or discipline.get("display_name")
            or discipline.get("code")
            or ""
        ).lower()
        pages = discipline.get("pages")
        if not isinstance(pages, list):
            continue

        for page in pages:
            if not isinstance(page, dict):
                continue
            page_id = str(page.get("page_id") or "").strip()
            if not page_id:
                continue

            page_name = str(
                page.get("sheet_number")
                or page.get("page_name")
                or page.get("title")
                or ""
            ).strip()
            title = str(page.get("title") or "").strip()

            if page_id not in fallback_page_ids:
                fallback_page_ids.append(page_id)

            if not query_tokens:
                continue

            haystack = f"{discipline_name} {page_name.lower()} {title.lower()}"
            score = 0
            for token in query_tokens:
                if token in haystack:
                    score += 2
                elif token.endswith("s") and len(token) > 2 and token[:-1] in haystack:
                    score += 1
            if score > 0:
                scored_entries.append((score, page_id, page_name))

    if scored_entries:
        scored_entries.sort(key=lambda item: (-item[0], _page_sort_key(item[2] or "")))
        ranked_page_ids: list[str] = []
        for _, page_id, _ in scored_entries:
            if page_id not in ranked_page_ids:
                ranked_page_ids.append(page_id)
            if len(ranked_page_ids) >= limit:
                break
        return ranked_page_ids

    return fallback_page_ids[:limit]


def _select_cover_index_fallback_page_ids(
    project_structure: dict[str, Any] | None,
    limit: int,
) -> list[str]:
    if not isinstance(project_structure, dict):
        return []

    disciplines = project_structure.get("disciplines")
    if not isinstance(disciplines, list):
        return []

    preferred_tokens = (
        "cover",
        "index",
        "sheet list",
        "legend",
        "general notes",
    )
    preferred: list[str] = []
    remaining: list[str] = []

    for discipline in disciplines:
        if not isinstance(discipline, dict):
            continue
        pages = discipline.get("pages")
        if not isinstance(pages, list):
            continue
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_id = str(page.get("page_id") or "").strip()
            if not page_id:
                continue
            title_bits = " ".join(
                str(page.get(key) or "")
                for key in ("sheet_number", "page_name", "title", "page_type")
            )
            normalized = _normalize_text(title_bits)
            if any(token in normalized for token in preferred_tokens):
                if page_id not in preferred:
                    preferred.append(page_id)
            elif page_id not in remaining:
                remaining.append(page_id)

    ordered = [*preferred, *remaining]
    return ordered[:limit]


def _dedupe_ids(values: list[str], limit: int | None = None) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        page_id = str(value or "").strip()
        if not page_id or page_id in seen:
            continue
        seen.add(page_id)
        deduped.append(page_id)
        if limit is not None and len(deduped) >= limit:
            break
    return deduped


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _infer_focus(query: str, must_terms: list[str]) -> str:
    if must_terms:
        return must_terms[0]
    tokens = [
        token
        for token in _extract_query_tokens(query)
        if token and token not in PAGE_NAVIGATION_STOP_TOKENS
    ]
    if not tokens:
        return _normalize_text(query)[:80]
    return " ".join(tokens[:4])


def _infer_preferred_disciplines(query: str, must_terms: list[str]) -> list[str]:
    haystack = _normalize_text(f"{query} {' '.join(must_terms)}")
    matches: list[str] = []
    for discipline, hints in DISCIPLINE_QUERY_HINTS.items():
        if any(_normalize_text(hint) and _normalize_text(hint) in haystack for hint in hints):
            matches.append(discipline)
    return matches[:3]


def _infer_area_or_level(query: str) -> str | None:
    query_lower = str(query or "").lower()
    level_match = re.search(r"\b(level|lvl|floor)\s*([0-9]+)\b", query_lower)
    if level_match:
        return f"{level_match.group(1)} {level_match.group(2)}"
    for token in ("roof", "basement", "mezzanine", "kitchen", "dining", "lobby", "north", "south", "east", "west"):
        if token in query_lower:
            return token
    return None


def _extract_entity_terms(query: str) -> list[str]:
    raw_entities = re.findall(r"\b[a-z]{1,6}-\d+[a-z0-9\-]*\b|\b[a-z]{2,8}\d+[a-z0-9\-]*\b", query.lower())
    normalized = [_normalize_text(entity) for entity in raw_entities if entity]
    deduped: list[str] = []
    seen: set[str] = set()
    for entity in normalized:
        if not entity or entity in seen:
            continue
        seen.add(entity)
        deduped.append(entity)
        if len(deduped) >= 6:
            break
    return deduped


def _select_exact_title_hits(
    query: str,
    must_terms: list[str],
    page_results: list[dict[str, Any]],
    limit: int = FAST_PAGE_LIMIT,
) -> list[str]:
    phrases: list[str] = []
    normalized_query = _normalize_text(query)
    if normalized_query and len(normalized_query) >= 4:
        phrases.append(normalized_query)
    for term in must_terms:
        normalized_term = _normalize_text(term)
        if normalized_term and len(normalized_term) >= 4 and normalized_term not in phrases:
            phrases.append(normalized_term)

    focus_phrase = _infer_focus(query, must_terms)
    normalized_focus = _normalize_text(focus_phrase)
    if normalized_focus and len(normalized_focus) >= 4 and normalized_focus not in phrases:
        phrases.append(normalized_focus)

    hits: list[str] = []
    for page in page_results:
        if not isinstance(page, dict):
            continue
        page_id = str(page.get("page_id") or "").strip()
        if not page_id:
            continue

        page_name = _normalize_text(str(page.get("page_name") or ""))
        sheet_card = page.get("sheet_card")
        if not isinstance(sheet_card, dict):
            sheet_card = {}
        reflection_title = _normalize_text(str(sheet_card.get("reflection_title") or ""))
        headings = sheet_card.get("reflection_headings")
        if not isinstance(headings, list):
            headings = []
        heading_text = _normalize_text(" ".join(str(h) for h in headings if h))
        reflection_headline = reflection_title or heading_text
        reflection = str(page.get("sheet_reflection") or "")
        if not reflection_headline and reflection:
            reflection_headline = _normalize_text(reflection.splitlines()[0])

        if not (page_name or reflection_headline or heading_text):
            continue

        for phrase in phrases:
            if not phrase:
                continue
            if page_name == phrase or phrase in page_name:
                hits.append(page_id)
                break
            if reflection_headline and (reflection_headline == phrase or phrase in reflection_headline):
                hits.append(page_id)
                break
            if heading_text and phrase in heading_text:
                hits.append(page_id)
                break

    return _dedupe_ids(hits, limit=limit)


def _hydrate_sheet_card(page: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(page, dict):
        return {}

    existing = page.get("sheet_card")
    if isinstance(existing, dict) and existing:
        return existing

    built = build_sheet_card(
        sheet_number=str(page.get("page_name") or ""),
        page_type=str(page.get("page_type") or ""),
        discipline_name=str(page.get("discipline") or ""),
        sheet_reflection=str(page.get("sheet_reflection") or page.get("content") or ""),
        master_index=page.get("master_index") if isinstance(page.get("master_index"), dict) else None,
        keywords=page.get("keywords") if isinstance(page.get("keywords"), list) else None,
        cross_references=page.get("cross_references"),
    )
    page["sheet_card"] = built
    return built


def _build_project_structure_page_lookup(project_structure: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    disciplines = project_structure.get("disciplines")
    if not isinstance(disciplines, list):
        return lookup

    for discipline in disciplines:
        if not isinstance(discipline, dict):
            continue
        discipline_name = str(
            discipline.get("name")
            or discipline.get("display_name")
            or discipline.get("code")
            or ""
        ).strip()
        pages = discipline.get("pages")
        if not isinstance(pages, list):
            continue
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_id = str(page.get("page_id") or "").strip()
            if not page_id:
                continue
            lookup[page_id] = {
                "page_name": str(
                    page.get("sheet_number")
                    or page.get("page_name")
                    or page.get("title")
                    or ""
                ).strip(),
                "discipline": discipline_name,
                "page_type": str(page.get("page_type") or "").strip(),
                "content": str(page.get("title") or "").strip(),
                "sheet_card": build_sheet_card(
                    sheet_number=str(
                        page.get("sheet_number")
                        or page.get("page_name")
                        or page.get("title")
                        or ""
                    ),
                    page_type=str(page.get("page_type") or ""),
                    discipline_name=discipline_name,
                    sheet_reflection=str(page.get("title") or ""),
                    master_index=None,
                    keywords=None,
                    cross_references=page.get("cross_references"),
                ),
            }
    return lookup


def _page_type_matches_preference(page_type: str, preferred_page_types: list[str]) -> bool:
    normalized_page_type = _normalize_page_type(page_type)
    if not normalized_page_type or not preferred_page_types:
        return False
    for preferred in preferred_page_types:
        aliases = ROUTER_PAGE_TYPE_ALIASES.get(preferred, {preferred})
        if normalized_page_type in aliases:
            return True
    return False


def _build_candidate_set(ids: list[str], limit: int = FAST_PAGE_LIMIT) -> dict[str, Any]:
    deduped = _dedupe_ids(ids, limit=limit)
    return {"count": len(deduped), "top_ids": deduped}


def _build_page_scoring_text(page: dict[str, Any]) -> tuple[str, str]:
    sheet_card = page.get("sheet_card")
    if not isinstance(sheet_card, dict):
        sheet_card = {}

    reflection_title = str(sheet_card.get("reflection_title") or "")
    reflection_summary = str(sheet_card.get("reflection_summary") or "")
    headings = sheet_card.get("reflection_headings")
    if not isinstance(headings, list):
        headings = []
    keywords = sheet_card.get("reflection_keywords")
    if not isinstance(keywords, list):
        keywords = []
    entities = sheet_card.get("reflection_entities")
    if not isinstance(entities, list):
        entities = []

    page_name = str(page.get("page_name") or "")
    discipline = str(page.get("discipline") or "")
    page_type = str(page.get("page_type") or "")
    content = str(page.get("content") or "")[:1200]

    title_blob = " ".join(
        part
        for part in (
            page_name,
            reflection_title,
            " ".join(str(h) for h in headings if h),
        )
        if part
    )
    text_blob = " ".join(
        part
        for part in (
            page_name,
            discipline,
            page_type,
            reflection_title,
            reflection_summary,
            " ".join(str(k) for k in keywords if k),
            " ".join(str(e) for e in entities if e),
            content,
        )
        if part
    )
    return _normalize_text(title_blob), _normalize_text(text_blob)


def _compute_rank_score_components(
    *,
    page_id: str,
    page: dict[str, Any],
    phrase_terms: list[str],
    preferred_page_types: list[str],
    preferred_disciplines: list[str],
    area_or_level: str | None,
    entity_terms: list[str],
    vector_rank_lookup: dict[str, int],
    source_hit_sets: dict[str, set[str]],
    query_allows_generic: bool,
) -> dict[str, float]:
    page_name = str(page.get("page_name") or "")
    discipline = str(page.get("discipline") or "")
    page_type = str(page.get("page_type") or "")
    sheet_card = page.get("sheet_card")
    if not isinstance(sheet_card, dict):
        sheet_card = {}

    title_norm, page_text_norm = _build_page_scoring_text(page)
    discipline_norm = _normalize_text(discipline)
    area_hint_norm = _normalize_text(str(area_or_level or ""))
    reflection_title_norm = _normalize_text(str(sheet_card.get("reflection_title") or ""))

    title_match = 0.0
    for phrase in phrase_terms:
        if not phrase:
            continue
        if title_norm == phrase:
            title_match = 1.0
            break
        if reflection_title_norm and reflection_title_norm == phrase:
            title_match = 1.0
            break
        if phrase in title_norm:
            title_match = max(title_match, 0.9)
        elif phrase in page_text_norm:
            title_match = max(title_match, 0.55)

    page_type_match = 1.0 if _page_type_matches_preference(page_type, preferred_page_types) else 0.0

    discipline_match = 0.0
    if preferred_disciplines and discipline_norm:
        if any(_normalize_text(pref) in discipline_norm for pref in preferred_disciplines):
            discipline_match = 1.0

    area_level_match = 1.0 if area_hint_norm and area_hint_norm in page_text_norm else 0.0

    entity_match = 0.0
    if entity_terms:
        hit_count = sum(1 for term in entity_terms if term and term in page_text_norm)
        entity_match = min(1.0, hit_count / float(len(entity_terms)))

    vector_rank_score = 0.0
    if page_id in vector_rank_lookup:
        vector_rank_score = 1.0 / float(vector_rank_lookup[page_id] + 1)

    exact_title_source_hit = 1.0 if page_id in source_hit_sets.get("exact_title_hits", set()) else 0.0
    lexical_source_match = 0.0
    if page_id in source_hit_sets.get("strict_keyword_hits", set()):
        lexical_source_match = 1.0
    elif page_id in source_hit_sets.get("reflection_keyword_hits", set()):
        lexical_source_match = 0.65

    penalties = 0.0
    title_for_penalty = " ".join(filter(None, [title_norm, reflection_title_norm]))
    if not query_allows_generic:
        if any(token in title_for_penalty for token in GENERIC_SHEET_TOKENS):
            penalties += 0.45
        if _normalize_page_type(page_type) in {"cover", "notes"}:
            penalties += 0.25
    if not page_name:
        penalties += 0.1

    total = (
        (title_match * 4.5)
        + (exact_title_source_hit * 4.5)
        + (lexical_source_match * 2.0)
        + (page_type_match * 2.0)
        + (discipline_match * 1.5)
        + (area_level_match * 1.2)
        + (entity_match * 1.5)
        + (vector_rank_score * 1.0)
        - penalties
    )

    return {
        "title_match": round(title_match, 4),
        "exact_title_source_hit": round(exact_title_source_hit, 4),
        "lexical_source_match": round(lexical_source_match, 4),
        "page_type_match": round(page_type_match, 4),
        "discipline_match": round(discipline_match, 4),
        "area_level_match": round(area_level_match, 4),
        "entity_match": round(entity_match, 4),
        "vector_rank": round(vector_rank_score, 4),
        "penalties": round(penalties, 4),
        "total": round(total, 4),
    }


def _rank_candidate_page_ids_v2(
    candidate_page_ids: list[str],
    *,
    page_lookup: dict[str, dict[str, Any]],
    query: str,
    must_terms: list[str],
    preferred_page_types: list[str],
    preferred_disciplines: list[str],
    area_or_level: str | None,
    entity_terms: list[str],
    vector_hits: list[str],
    source_hit_sets: dict[str, set[str]],
    limit: int,
) -> list[str]:
    if not candidate_page_ids:
        return []

    query_norm = _normalize_text(query)
    phrase_terms = [_normalize_text(term) for term in must_terms if term]
    if query_norm and len(query_norm) >= 4:
        phrase_terms = [query_norm, *phrase_terms]
    phrase_terms = [phrase for phrase in phrase_terms if phrase]

    vector_rank_lookup = {page_id: index for index, page_id in enumerate(vector_hits)}
    query_allows_generic = any(
        token in query_norm
        for token in ("cover", "index", "legend", "sheet list", "notes", "schedule")
    )

    scored: list[tuple[str, float, list[Any]]] = []
    for page_id in _dedupe_ids(candidate_page_ids):
        page = page_lookup.get(page_id, {})
        score_components = _compute_rank_score_components(
            page_id=page_id,
            page=page,
            phrase_terms=phrase_terms,
            preferred_page_types=preferred_page_types,
            preferred_disciplines=preferred_disciplines,
            area_or_level=area_or_level,
            entity_terms=entity_terms,
            vector_rank_lookup=vector_rank_lookup,
            source_hit_sets=source_hit_sets,
            query_allows_generic=query_allows_generic,
        )
        score_total = float(score_components.get("total", 0.0))
        page_name = str(page.get("page_name") or "")
        scored.append((page_id, score_total, _page_sort_key(page_name)))

    scored.sort(key=lambda item: (-item[1], item[2], item[0]))
    return [page_id for page_id, _, _ in scored[:limit]]


def _build_rank_breakdown(
    query: str,
    ordered_page_ids: list[str],
    page_lookup: dict[str, dict[str, Any]],
    *,
    must_terms: list[str],
    preferred_page_types: list[str],
    preferred_disciplines: list[str],
    area_or_level: str | None,
    entity_terms: list[str],
    vector_hits: list[str],
    source_hit_sets: dict[str, set[str]],
    top_n: int = FAST_PAGE_LIMIT,
) -> list[dict[str, Any]]:
    if not ordered_page_ids:
        return []

    query_norm = _normalize_text(query)
    phrase_terms = [_normalize_text(term) for term in must_terms if term]
    if query_norm and len(query_norm) >= 4:
        phrase_terms = [query_norm, *phrase_terms]
    phrase_terms = [phrase for phrase in phrase_terms if phrase]

    vector_rank_lookup = {page_id: index for index, page_id in enumerate(vector_hits)}
    query_allows_generic = any(
        token in query_norm
        for token in ("cover", "index", "legend", "sheet list", "notes", "schedule")
    )

    ranked: list[dict[str, Any]] = []
    for selection_rank, page_id in enumerate(ordered_page_ids[:top_n], start=1):
        page = page_lookup.get(page_id, {})
        score_components = _compute_rank_score_components(
            page_id=page_id,
            page=page,
            phrase_terms=phrase_terms,
            preferred_page_types=preferred_page_types,
            preferred_disciplines=preferred_disciplines,
            area_or_level=area_or_level,
            entity_terms=entity_terms,
            vector_rank_lookup=vector_rank_lookup,
            source_hit_sets=source_hit_sets,
            query_allows_generic=query_allows_generic,
        )

        ranked.append(
            {
                "selection_rank": selection_rank,
                "page_id": page_id,
                "page_name": str(page.get("page_name") or "") or None,
                "score_components": score_components,
                "source_hits": {
                    key: page_id in value
                    for key, value in source_hit_sets.items()
                },
            }
        )

    return ranked


def _build_final_selection_trace(
    ordered_page_ids: list[str],
    page_lookup: dict[str, dict[str, Any]],
    *,
    target_page_limit: int,
    page_navigation_intent: bool,
    source_hit_sets: dict[str, set[str]],
    selector_relevance_by_id: dict[str, str],
    cross_reference_page_ids: set[str],
) -> dict[str, Any]:
    if not ordered_page_ids:
        return {
            "primary": [],
            "supporting": [],
            "target_page_limit": target_page_limit,
        }

    if page_navigation_intent:
        primary_limit = min(len(ordered_page_ids), max(1, min(4, target_page_limit)))
    else:
        primary_limit = min(len(ordered_page_ids), max(1, min(2, target_page_limit)))

    primary_ids = ordered_page_ids[:primary_limit]
    supporting_ids = ordered_page_ids[primary_limit:]

    def _reason_codes(page_id: str) -> list[str]:
        codes: list[str] = []
        if page_id in source_hit_sets.get("exact_title_hits", set()):
            codes.append("exact_title_match")
        if page_id in source_hit_sets.get("strict_keyword_hits", set()):
            codes.append("strict_keyword_match")
        elif page_id in source_hit_sets.get("reflection_keyword_hits", set()):
            codes.append("reflection_keyword_hit")
        if page_id in source_hit_sets.get("vector_hits", set()):
            codes.append("vector_hit")
        if page_id in source_hit_sets.get("region_hits", set()):
            codes.append("region_hit")
        if page_id in source_hit_sets.get("project_tree_hits", set()):
            codes.append("project_tree_hit")
        if page_id in source_hit_sets.get("smart_selector_hits", set()):
            codes.append("smart_selector_hit")
        if page_id in cross_reference_page_ids:
            codes.append("cross_reference")
        if not codes:
            codes.append("fallback")
        return codes

    def _entry(page_id: str) -> dict[str, Any]:
        page = page_lookup.get(page_id, {})
        selector_reason = selector_relevance_by_id.get(page_id)
        reason_codes = _reason_codes(page_id)
        return {
            "page_id": page_id,
            "page_name": page.get("page_name") or None,
            "reason_codes": reason_codes,
            "reason": selector_reason or ", ".join(reason_codes),
        }

    return {
        "primary": [_entry(page_id) for page_id in primary_ids],
        "supporting": [_entry(page_id) for page_id in supporting_ids],
        "target_page_limit": target_page_limit,
    }


def _normalize_region_bbox(region: dict[str, Any]) -> list[float] | None:
    if not isinstance(region, dict):
        return None

    bbox = region.get("bbox")
    raw_x0: Any = 0.0
    raw_y0: Any = 0.0
    raw_x1: Any = 0.0
    raw_y1: Any = 0.0

    if isinstance(bbox, dict):
        raw_x0 = bbox.get("x0", bbox.get("x", 0.0))
        raw_y0 = bbox.get("y0", bbox.get("y", 0.0))
        raw_x1 = bbox.get("x1")
        raw_y1 = bbox.get("y1")
        if raw_x1 is None and bbox.get("width") is not None:
            raw_x1 = _coerce_float(raw_x0) + _coerce_float(bbox.get("width"))
        if raw_y1 is None and bbox.get("height") is not None:
            raw_y1 = _coerce_float(raw_y0) + _coerce_float(bbox.get("height"))
    elif isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        raw_x0, raw_y0, raw_x1, raw_y1 = bbox
    else:
        return None

    x0 = _coerce_float(raw_x0)
    y0 = _coerce_float(raw_y0)
    x1 = _coerce_float(raw_x1)
    y1 = _coerce_float(raw_y1)

    def _to_unit(value: float) -> float:
        abs_value = abs(value)
        if abs_value <= 1.0:
            return value
        if abs_value <= 1000.0:
            return value / 1000.0
        return value

    x0 = _to_unit(x0)
    y0 = _to_unit(y0)
    x1 = _to_unit(x1)
    y1 = _to_unit(y1)

    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0

    if max(abs(x0), abs(y0), abs(x1), abs(y1)) > 1.0:
        return None

    x0 = max(0.0, min(1.0, x0))
    y0 = max(0.0, min(1.0, y0))
    x1 = max(0.0, min(1.0, x1))
    y1 = max(0.0, min(1.0, y1))

    if x1 <= x0 or y1 <= y0:
        return None
    return [round(x0, 6), round(y0, 6), round(x1, 6), round(y1, 6)]


def _append_region_index_text(value: Any, output: list[str], *, limit: int = 64) -> None:
    if len(output) >= limit:
        return

    if isinstance(value, dict):
        for nested in value.values():
            _append_region_index_text(nested, output, limit=limit)
            if len(output) >= limit:
                break
        return

    if isinstance(value, list):
        for nested in value:
            _append_region_index_text(nested, output, limit=limit)
            if len(output) >= limit:
                break
        return

    text = str(value or "").strip()
    if text:
        output.append(text)


def _build_region_text_blob(region: dict[str, Any]) -> tuple[str, str]:
    region_type = str(region.get("type") or "")
    label = str(region.get("label") or region.get("name") or "")
    detail_number = str(region.get("detail_number") or region.get("detailNumber") or "")
    shows = str(region.get("shows") or "")

    region_index = region.get("region_index")
    if not isinstance(region_index, dict):
        region_index = {}

    region_index_parts: list[str] = []
    _append_region_index_text(region_index, region_index_parts)
    region_index_text = " ".join(region_index_parts)

    title_blob = " ".join(part for part in (label, detail_number) if part)
    text_blob = " ".join(part for part in (region_type, label, detail_number, shows, region_index_text) if part)
    return _normalize_text(title_blob), _normalize_text(text_blob)


def _infer_region_type_preferences(
    query: str,
    must_terms: list[str],
    preferred_page_types: list[str],
) -> dict[str, float]:
    haystack = _normalize_text(f"{query} {' '.join(must_terms)} {' '.join(preferred_page_types)}")
    if not haystack:
        return {}

    prefs: dict[str, float] = {}

    def _boost(values: list[str], amount: float) -> None:
        for value in values:
            current = prefs.get(value, 0.0)
            prefs[value] = max(current, amount)

    if any(token in haystack for token in ("schedule", "panel", "tabulation", "table")):
        _boost(["schedule"], 1.0)
    if any(token in haystack for token in ("detail", "section", "elevation", "callout", "curb", "hood")):
        _boost(["detail"], 1.0)
    if any(token in haystack for token in ("note", "notes", "general note", "keynote")):
        _boost(["notes", "legend"], 0.85)
    if any(token in haystack for token in ("legend", "symbol")):
        _boost(["legend"], 1.0)
    if any(token in haystack for token in ("title block", "sheet number", "revision block")):
        _boost(["title_block"], 1.0)
    if any(token in haystack for token in ("where", "location", "locate", "plan", "floor plan", "area", "room")):
        _boost(["plan", "floor_plan", "detail"], 0.65)

    return prefs


def _normalize_region_type(region: dict[str, Any]) -> str:
    region_type = _normalize_text(str(region.get("type") or "")).replace(" ", "_")
    if not region_type:
        return "unknown"
    if region_type == "floorplan":
        return "floor_plan"
    return region_type


def _build_med_region_reason(
    region_type: str,
    label_match: float,
    type_match: float,
    similarity: float,
    entity_match: float,
) -> str:
    reasons: list[str] = []
    if label_match >= 0.8:
        reasons.append("strong label match")
    elif label_match >= 0.4:
        reasons.append("label keyword match")
    if type_match >= 0.9:
        reasons.append(f"{region_type} type match")
    elif type_match >= 0.5:
        reasons.append("type hint match")
    if similarity >= 0.8:
        reasons.append("high semantic similarity")
    elif similarity >= 0.55:
        reasons.append("semantic similarity")
    if entity_match >= 0.8:
        reasons.append("entity/tag match")
    if not reasons:
        reasons.append("best available region candidate")
    return ", ".join(reasons[:2])


def _score_med_region(
    *,
    page_id: str,
    page_name: str,
    page_type: str,
    region: dict[str, Any],
    query: str,
    must_terms: list[str],
    preferred_page_types: list[str],
    entity_terms: list[str],
    region_type_preferences: dict[str, float],
) -> dict[str, Any]:
    region_type = _normalize_region_type(region)
    title_norm, text_norm = _build_region_text_blob(region)
    query_norm = _normalize_text(query)

    phrase_terms = [_normalize_text(term) for term in must_terms if term]
    if query_norm and len(query_norm) >= 4:
        phrase_terms = [query_norm, *phrase_terms]
    phrase_terms = [term for term in phrase_terms if term]

    label_match = 0.0
    for term in phrase_terms:
        if not term:
            continue
        if term == title_norm:
            label_match = 1.0
            break
        if term in title_norm:
            label_match = max(label_match, 0.9)
        elif term in text_norm:
            label_match = max(label_match, 0.5)

    similarity = _coerce_float(region.get("_similarity"), 0.0)
    if similarity < 0:
        similarity = 0.0
    if similarity > 1.0:
        similarity = min(1.0, similarity)

    type_match = region_type_preferences.get(region_type, 0.0)
    if type_match <= 0 and not region_type_preferences:
        if region_type in {"schedule", "detail", "notes", "plan", "floor_plan"}:
            type_match = 0.25
    if type_match <= 0 and region_type in {"legend", "title_block"}:
        type_match = 0.1

    entity_match = 0.0
    if entity_terms and text_norm:
        hit_count = sum(1 for term in entity_terms if term and term in text_norm)
        entity_match = min(1.0, hit_count / float(len(entity_terms)))

    page_type_match = 1.0 if _page_type_matches_preference(page_type, preferred_page_types) else 0.0

    penalties = 0.0
    if region_type in {"title_block", "legend"} and type_match < 0.5:
        penalties += 0.35
    if not title_norm:
        penalties += 0.08

    bbox = _normalize_region_bbox(region)
    if bbox is None:
        penalties += 0.45

    total = (
        (similarity * 3.1)
        + (label_match * 2.3)
        + (type_match * 1.8)
        + (entity_match * 1.2)
        + (page_type_match * 0.5)
        - penalties
    )

    reason = _build_med_region_reason(region_type, label_match, type_match, similarity, entity_match)
    region_id = str(region.get("id") or "").strip()
    if not region_id:
        detail_number = str(region.get("detail_number") or region.get("detailNumber") or "").strip()
        region_id = f"{region_type}:{detail_number}" if detail_number else f"{region_type}:unnamed"

    return {
        "page_id": page_id,
        "page_name": page_name,
        "page_type": page_type,
        "region_id": region_id,
        "label": str(region.get("label") or region.get("name") or region_type).strip() or region_type,
        "region_type": region_type,
        "bbox": bbox,
        "score": round(total, 4),
        "reason": reason,
        "score_components": {
            "semantic_similarity": round(similarity, 4),
            "label_match": round(label_match, 4),
            "type_match": round(type_match, 4),
            "entity_match": round(entity_match, 4),
            "page_type_match": round(page_type_match, 4),
            "penalties": round(penalties, 4),
            "total": round(total, 4),
        },
    }


def _select_med_region_candidates(
    *,
    ordered_page_ids: list[str],
    page_map: dict[str, Page],
    region_matches: dict[str, list[dict[str, Any]]],
    query: str,
    must_terms: list[str],
    preferred_page_types: list[str],
    entity_terms: list[str],
    total_limit: int = MED_TOTAL_HIGHLIGHT_LIMIT,
    per_page_limit: int = MED_HIGHLIGHTS_PER_PAGE,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    region_type_preferences = _infer_region_type_preferences(query, must_terms, preferred_page_types)
    page_order_lookup = {page_id: idx for idx, page_id in enumerate(ordered_page_ids)}

    per_page_ranked: list[dict[str, Any]] = []
    aggregate_candidates: list[dict[str, Any]] = []

    for page_id in ordered_page_ids:
        page_obj = page_map.get(page_id)
        if not page_obj:
            continue

        page_name = str(getattr(page_obj, "page_name", "") or "")
        page_type = str(getattr(page_obj, "page_type", "") or "")

        candidate_regions: list[dict[str, Any]] = []
        seen_region_keys: set[str] = set()

        matched_regions = region_matches.get(page_id) or []
        for idx, region in enumerate(matched_regions):
            if not isinstance(region, dict):
                continue
            copied = dict(region)
            region_id = str(copied.get("id") or f"matched_{idx}").strip()
            if region_id in seen_region_keys:
                continue
            seen_region_keys.add(region_id)
            candidate_regions.append(copied)

        page_regions = getattr(page_obj, "regions", None)
        if isinstance(page_regions, list):
            for idx, region in enumerate(page_regions):
                if not isinstance(region, dict):
                    continue
                copied = dict(region)
                region_id = str(copied.get("id") or f"page_{idx}").strip()
                if region_id in seen_region_keys:
                    continue
                seen_region_keys.add(region_id)
                candidate_regions.append(copied)

        scored_regions: list[dict[str, Any]] = []
        for region in candidate_regions:
            scored = _score_med_region(
                page_id=page_id,
                page_name=page_name,
                page_type=page_type,
                region=region,
                query=query,
                must_terms=must_terms,
                preferred_page_types=preferred_page_types,
                entity_terms=entity_terms,
                region_type_preferences=region_type_preferences,
            )
            if scored.get("bbox") is None:
                continue
            scored_regions.append(scored)

        scored_regions.sort(
            key=lambda item: (
                -float(item.get("score") or 0.0),
                _page_sort_key(str(item.get("label") or "")),
                str(item.get("region_id") or ""),
            )
        )

        top_for_page = scored_regions[:max(1, per_page_limit)]
        per_page_ranked.append(
            {
                "page_id": page_id,
                "page_name": page_name or None,
                "regions": top_for_page,
            }
        )
        aggregate_candidates.extend(top_for_page)

    aggregate_candidates.sort(
        key=lambda item: (
            -float(item.get("score") or 0.0),
            page_order_lookup.get(str(item.get("page_id")), 10_000),
            _page_sort_key(str(item.get("label") or "")),
            str(item.get("region_id") or ""),
        )
    )

    selected: list[dict[str, Any]] = []
    page_counts: dict[str, int] = {}
    seen_keys: set[str] = set()
    for candidate in aggregate_candidates:
        page_id = str(candidate.get("page_id") or "")
        region_id = str(candidate.get("region_id") or "")
        if not page_id:
            continue
        key = f"{page_id}:{region_id}"
        if key in seen_keys:
            continue
        if page_counts.get(page_id, 0) >= per_page_limit:
            continue
        selected.append(candidate)
        seen_keys.add(key)
        page_counts[page_id] = page_counts.get(page_id, 0) + 1
        if len(selected) >= max(1, total_limit):
            break

    return selected, per_page_ranked


def _build_med_mode_response_text(
    ordered_page_ids: list[str],
    page_map: dict[str, Page],
    selected_regions: list[dict[str, Any]],
) -> str:
    if not ordered_page_ids:
        return "I couldn't find strong sheets for this request yet."

    regions_by_page: dict[str, list[str]] = {}
    for region in selected_regions:
        page_id = str(region.get("page_id") or "")
        label = str(region.get("label") or "").strip()
        if not page_id:
            continue
        bucket = regions_by_page.setdefault(page_id, [])
        if label and label not in bucket:
            bucket.append(label)

    page_notes: list[str] = []
    for page_id in ordered_page_ids[:MED_PAGE_LIMIT]:
        page = page_map.get(page_id)
        if not page:
            continue
        page_name = str(getattr(page, "page_name", "") or page_id)
        labels = regions_by_page.get(page_id) or []
        if labels:
            page_notes.append(f"{page_name} ({', '.join(labels[:2])})")
        else:
            page_notes.append(f"{page_name} (best available region)")
        if len(page_notes) >= 3:
            break

    if page_notes:
        return (
            "I pulled the best sheets and highlighted the areas to check first: "
            + "; ".join(page_notes)
            + "."
        )
    return "I pulled the best sheets and highlighted likely areas to check first."


def _infer_deep_evidence_targets(query: str, query_tokens: list[str]) -> list[dict[str, str]]:
    """Infer likely evidence categories Deep mode should verify from the query."""
    haystack = _normalize_text(query)
    targets: list[dict[str, str]] = []
    seen_categories: set[str] = set()

    def _add_target(category: str, hint: str) -> None:
        if category in seen_categories:
            return
        seen_categories.add(category)
        targets.append({"category": category, "hint": hint})

    if any(token in haystack for token in ("dimension", "dimensions", "size", "height", "width", "depth", "\"", "ft", "inch")):
        _add_target("dimensions", "verify exact dimensions and units")
    if any(token in haystack for token in ("symbol", "legend", "callout", "section", "elevation", "detail")):
        _add_target("symbol", "verify symbol/callout identity and reference")
    if any(token in haystack for token in ("tag", "label", "room", "equipment", "panel", "wic", "ahu", "rtu")):
        _add_target("tag", "verify equipment/room/panel tags")
    if any(token in haystack for token in ("schedule", "table", "spec", "specification", "notes", "note")):
        _add_target("schedule_or_note", "verify schedule row or note text")

    focus_tokens = [token for token in query_tokens if len(token) >= 3][:3]
    if focus_tokens:
        _add_target("query_anchor", f"verify query anchors: {', '.join(focus_tokens)}")

    if not targets:
        _add_target("text", "verify exact on-sheet text tied to the query")

    return targets[:5]


def _build_deep_region_prompt_payload(region: dict[str, Any]) -> dict[str, Any]:
    """Compact region payload passed to Deep vision prompts."""
    bbox = region.get("bbox")
    bbox_payload: dict[str, float] | None = None
    if isinstance(bbox, list) and len(bbox) == 4:
        bbox_payload = {
            "x0": float(bbox[0]),
            "y0": float(bbox[1]),
            "x1": float(bbox[2]),
            "y1": float(bbox[3]),
        }

    payload = {
        "id": str(region.get("region_id") or ""),
        "type": str(region.get("region_type") or ""),
        "label": str(region.get("label") or ""),
        "bbox": bbox_payload,
        "score": _coerce_float(region.get("score"), 0.0),
        "reason": str(region.get("reason") or ""),
    }
    region_index = region.get("region_index")
    if region_index is not None:
        payload["regionIndex"] = region_index
    detail_number = region.get("detail_number")
    if detail_number:
        payload["detailNumber"] = detail_number
    return payload


def _group_deep_regions_by_page(regions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for region in regions:
        page_id = str(region.get("page_id") or "").strip()
        if not page_id:
            continue
        grouped.setdefault(page_id, []).append(region)
    return grouped


def _build_deep_verification_plan(
    *,
    query: str,
    ordered_page_ids: list[str],
    page_map: dict[str, Page],
    region_matches: dict[str, list[dict[str, Any]]],
    must_terms: list[str] | None = None,
    preferred_page_types: list[str] | None = None,
    max_pages: int = DEEP_PAGE_LIMIT,
    max_candidate_regions: int = DEEP_CANDIDATE_REGION_LIMIT,
    max_expansion_regions: int = DEEP_EXPANSION_REGION_LIMIT,
    max_micro_crops: int = DEEP_MICRO_CROP_LIMIT,
) -> dict[str, Any]:
    """
    Build deterministic Deep verification plan from ranked pages/regions.

    This keeps Deep mode bounded and candidate-first before any expensive vision pass.
    """
    query_tokens = _extract_query_tokens(query)
    must_terms = [str(term).strip() for term in (must_terms or []) if str(term).strip()]
    if not must_terms:
        must_terms = query_tokens[:4]
    preferred_page_types = [str(value).strip() for value in (preferred_page_types or []) if str(value).strip()]

    evidence_targets = _infer_deep_evidence_targets(query, query_tokens)
    entity_terms = _extract_entity_terms(query)
    region_type_preferences = _infer_region_type_preferences(query, must_terms, preferred_page_types)

    limited_page_ids = ordered_page_ids[:max(1, max_pages)]
    page_order_lookup = {page_id: index for index, page_id in enumerate(limited_page_ids)}

    all_candidate_scored: list[dict[str, Any]] = []
    all_expansion_scored: list[dict[str, Any]] = []
    page_selection: list[dict[str, Any]] = []

    for page_id in limited_page_ids:
        page_obj = page_map.get(page_id)
        if not page_obj:
            continue

        page_name = str(getattr(page_obj, "page_name", "") or "")
        page_type = str(getattr(page_obj, "page_type", "") or "")
        discipline_obj = getattr(page_obj, "discipline", None)
        discipline_name = str(getattr(discipline_obj, "display_name", "") or "") if discipline_obj else ""

        raw_candidate_regions = region_matches.get(page_id) or []
        raw_page_regions = page_obj.regions if isinstance(page_obj.regions, list) else []

        seen_region_ids: set[str] = set()
        scored_candidates_for_page = 0
        scored_expansions_for_page = 0

        for idx, region in enumerate(raw_candidate_regions):
            if not isinstance(region, dict):
                continue
            region_copy = dict(region)
            region_id = str(region_copy.get("id") or f"candidate_{idx}").strip()
            if not region_id or region_id in seen_region_ids:
                continue
            seen_region_ids.add(region_id)

            scored = _score_med_region(
                page_id=page_id,
                page_name=page_name,
                page_type=page_type,
                region=region_copy,
                query=query,
                must_terms=must_terms,
                preferred_page_types=preferred_page_types,
                entity_terms=entity_terms,
                region_type_preferences=region_type_preferences,
            )
            if scored.get("bbox") is None:
                continue
            scored["origin"] = "candidate_match"
            scored["page_order"] = page_order_lookup.get(page_id, 10_000)
            if region_copy.get("regionIndex") is not None:
                scored["region_index"] = region_copy.get("regionIndex")
            detail_number = region_copy.get("detailNumber") or region_copy.get("detail_number")
            if detail_number is not None:
                scored["detail_number"] = str(detail_number)

            all_candidate_scored.append(scored)
            scored_candidates_for_page += 1

        for idx, region in enumerate(raw_page_regions):
            if not isinstance(region, dict):
                continue
            region_copy = dict(region)
            region_id = str(region_copy.get("id") or f"region_{idx}").strip()
            if not region_id or region_id in seen_region_ids:
                continue
            seen_region_ids.add(region_id)

            scored = _score_med_region(
                page_id=page_id,
                page_name=page_name,
                page_type=page_type,
                region=region_copy,
                query=query,
                must_terms=must_terms,
                preferred_page_types=preferred_page_types,
                entity_terms=entity_terms,
                region_type_preferences=region_type_preferences,
            )
            if scored.get("bbox") is None:
                continue
            scored["origin"] = "page_region"
            scored["page_order"] = page_order_lookup.get(page_id, 10_000)
            if region_copy.get("regionIndex") is not None:
                scored["region_index"] = region_copy.get("regionIndex")
            detail_number = region_copy.get("detailNumber") or region_copy.get("detail_number")
            if detail_number is not None:
                scored["detail_number"] = str(detail_number)

            all_expansion_scored.append(scored)
            scored_expansions_for_page += 1

        page_selection.append(
            {
                "page_id": page_id,
                "page_name": page_name or None,
                "discipline": discipline_name or None,
                "page_type": page_type or None,
                "candidate_pool_count": len(raw_candidate_regions),
                "expansion_pool_count": len(raw_page_regions),
                "scored_candidate_count": scored_candidates_for_page,
                "scored_expansion_count": scored_expansions_for_page,
            }
        )

    def _sort_regions(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            values,
            key=lambda item: (
                -_coerce_float(item.get("score"), 0.0),
                int(item.get("page_order", 10_000)),
                _page_sort_key(str(item.get("label") or "")),
                str(item.get("region_id") or ""),
            ),
        )

    sorted_candidates = _sort_regions(all_candidate_scored)
    sorted_expansions = _sort_regions(all_expansion_scored)

    selected_candidates: list[dict[str, Any]] = []
    selected_keys: set[str] = set()
    for region in sorted_candidates:
        page_id = str(region.get("page_id") or "")
        region_id = str(region.get("region_id") or "")
        if not page_id or not region_id:
            continue
        key = f"{page_id}:{region_id}"
        if key in selected_keys:
            continue
        selected_keys.add(key)
        selected_candidates.append(region)
        if len(selected_candidates) >= max(1, max_candidate_regions):
            break

    selected_expansions: list[dict[str, Any]] = []
    for region in sorted_expansions:
        page_id = str(region.get("page_id") or "")
        region_id = str(region.get("region_id") or "")
        if not page_id or not region_id:
            continue
        key = f"{page_id}:{region_id}"
        if key in selected_keys:
            continue
        selected_keys.add(key)
        selected_expansions.append(region)
        if len(selected_expansions) >= max(0, max_expansion_regions):
            break

    candidate_by_page = _group_deep_regions_by_page(selected_candidates)
    expansion_by_page = _group_deep_regions_by_page(selected_expansions)

    candidate_region_ids = [
        str(region.get("region_id"))
        for region in selected_candidates
        if region.get("region_id")
    ]
    expansion_region_ids = [
        str(region.get("region_id"))
        for region in selected_expansions
        if region.get("region_id")
    ]

    verification_steps = [
        {
            "pass": 1,
            "name": "candidate_region_crop",
            "objective": "Start with top candidate regions before expanding search.",
            "max_regions": len(candidate_region_ids),
            "region_ids": candidate_region_ids,
        },
        {
            "pass": 2,
            "name": "cluster_tight_crop",
            "objective": "Use tighter crops around text/dimension/symbol clusters from pass 1.",
            "max_regions": len(candidate_region_ids) + len(expansion_region_ids),
            "region_ids": [*candidate_region_ids, *expansion_region_ids],
        },
        {
            "pass": 3,
            "name": "micro_crop_disambiguation",
            "objective": "Use micro-crops only for unresolved or ambiguous reads.",
            "max_crops": max(0, max_micro_crops),
        },
    ]

    return {
        "query_plan": {
            "intent": "verification",
            "query_tokens": query_tokens[:8],
            "must_terms": must_terms[:4],
            "preferred_page_types": preferred_page_types[:3],
            "evidence_targets": evidence_targets,
        },
        "budgets": {
            "max_pages": max(1, max_pages),
            "max_candidate_regions": max(1, max_candidate_regions),
            "max_expansion_regions": max(0, max_expansion_regions),
            "max_micro_crops": max(0, max_micro_crops),
        },
        "page_selection": page_selection,
        "candidate_regions": selected_candidates,
        "expansion_regions": selected_expansions,
        "candidate_regions_by_page": {
            page_id: [_build_deep_region_prompt_payload(region) for region in regions]
            for page_id, regions in candidate_by_page.items()
        },
        "expansion_regions_by_page": {
            page_id: [_build_deep_region_prompt_payload(region) for region in regions]
            for page_id, regions in expansion_by_page.items()
        },
        "steps": verification_steps,
    }


def _build_deep_highlight_specs_from_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map Deep findings to resolve_highlights-compatible grouped specs."""
    grouped: dict[str, dict[str, Any]] = {}
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        page_id = str(finding.get("page_id") or finding.get("pageId") or "").strip()
        if not page_id:
            continue

        entry = grouped.setdefault(
            page_id,
            {
                "page_id": page_id,
                "semantic_refs": [],
                "bboxes": [],
                "source": "agent",
            },
        )

        refs_raw = finding.get("semantic_refs")
        if not isinstance(refs_raw, list):
            refs_raw = finding.get("semanticRefs")
        if isinstance(refs_raw, list):
            seen_ref_keys = {str(ref) for ref in entry["semantic_refs"]}
            for ref in refs_raw:
                normalized_ref: Any = ref
                if normalized_ref is None or isinstance(normalized_ref, bool):
                    continue
                if isinstance(normalized_ref, float):
                    if normalized_ref.is_integer():
                        normalized_ref = int(normalized_ref)
                    else:
                        continue
                elif isinstance(normalized_ref, str):
                    normalized_ref = normalized_ref.strip()
                    if not normalized_ref:
                        continue
                    if normalized_ref.isdigit():
                        normalized_ref = int(normalized_ref)
                elif not isinstance(normalized_ref, int):
                    continue

                ref_key = str(normalized_ref)
                if ref_key in seen_ref_keys:
                    continue
                entry["semantic_refs"].append(normalized_ref)
                seen_ref_keys.add(ref_key)
                if len(entry["semantic_refs"]) >= 64:
                    break

        bbox = finding.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            entry["bboxes"].append(
                {
                    "bbox": bbox,
                    "category": str(finding.get("category") or "finding"),
                    "source_text": str(
                        finding.get("source_text")
                        or finding.get("sourceText")
                        or finding.get("content")
                        or ""
                    ).strip(),
                    "confidence": str(finding.get("confidence") or "").strip() or None,
                }
            )

    specs: list[dict[str, Any]] = []
    for spec in grouped.values():
        if not spec.get("semantic_refs") and not spec.get("bboxes"):
            continue
        specs.append(spec)
    return specs


def _deep_finding_has_evidence(finding: dict[str, Any]) -> bool:
    source_text = str(finding.get("source_text") or finding.get("sourceText") or "").strip()
    semantic_refs = finding.get("semantic_refs")
    if not isinstance(semantic_refs, list):
        semantic_refs = finding.get("semanticRefs")
    bbox = finding.get("bbox")
    has_bbox = isinstance(bbox, list) and len(bbox) == 4
    has_refs = isinstance(semantic_refs, list) and len(semantic_refs) > 0
    return bool(source_text) and (has_bbox or has_refs)


def _normalize_deep_findings_for_contract(
    findings: list[dict[str, Any]],
    *,
    enforce_verified_evidence: bool,
) -> tuple[list[dict[str, Any]], int]:
    normalized: list[dict[str, Any]] = []
    downgraded_verified_count = 0
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        item = dict(finding)
        confidence = str(item.get("confidence") or "").strip()
        if (
            enforce_verified_evidence
            and confidence == "verified_via_zoom"
            and not _deep_finding_has_evidence(item)
        ):
            item["confidence"] = "medium"
            downgraded_verified_count += 1
        normalized.append(item)
    return normalized, downgraded_verified_count


def _summarize_deep_findings(findings: list[dict[str, Any]]) -> dict[str, int]:
    verified = 0
    high = 0
    medium = 0
    evidence_complete = 0
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        confidence = str(finding.get("confidence") or "").strip()
        if confidence == "verified_via_zoom":
            verified += 1
        elif confidence == "high":
            high += 1
        elif confidence == "medium":
            medium += 1
        if _deep_finding_has_evidence(finding):
            evidence_complete += 1
    return {
        "total": len(findings),
        "verified_via_zoom": verified,
        "high": high,
        "medium": medium,
        "evidence_complete": evidence_complete,
        "evidence_incomplete": max(0, len(findings) - evidence_complete),
    }


def _extract_deep_pass_counts(
    findings: list[dict[str, Any]],
    provider_execution_summary: Any,
) -> dict[str, int]:
    """Normalize Deep pass counters from provider summary, then fallback to finding-level inference."""
    counts: dict[str, int] = {"pass_1": 0, "pass_2": 0, "pass_3": 0}
    alias_map = {
        "pass_1": (
            "pass_1",
            "pass1",
            "pass_1_count",
            "pass1_count",
            "pass_1_crop_count",
            "pass_1_crops",
            "candidate_crop_count",
            "1",
        ),
        "pass_2": (
            "pass_2",
            "pass2",
            "pass_2_count",
            "pass2_count",
            "pass_2_crop_count",
            "pass_2_crops",
            "cluster_crop_count",
            "2",
        ),
        "pass_3": (
            "pass_3",
            "pass3",
            "pass_3_count",
            "pass3_count",
            "pass_3_crop_count",
            "pass_3_crops",
            "micro_crop_count",
            "3",
        ),
    }

    def _consume(container: Any) -> None:
        if not isinstance(container, dict):
            return
        for canonical, keys in alias_map.items():
            for key in keys:
                if key not in container:
                    continue
                value = container.get(key)
                try:
                    parsed = int(value)
                except (TypeError, ValueError):
                    continue
                if parsed >= 0:
                    counts[canonical] = parsed
                    break

    _consume(provider_execution_summary)
    if isinstance(provider_execution_summary, dict):
        _consume(provider_execution_summary.get("pass_counts"))
        _consume(provider_execution_summary.get("passes"))

    derived = {"pass_1": 0, "pass_2": 0, "pass_3": 0}
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        try:
            pass_index = int(finding.get("verification_pass"))
        except (TypeError, ValueError):
            pass_index = 0
        if pass_index in (1, 2, 3):
            derived[f"pass_{pass_index}"] += 1

    for key in ("pass_1", "pass_2", "pass_3"):
        if counts[key] <= 0 and derived[key] > 0:
            counts[key] = derived[key]

    counts["pass_total"] = counts["pass_1"] + counts["pass_2"] + counts["pass_3"]
    return counts


def _filter_semantic_index(
    semantic_index: dict | None,
    query_tokens: list[str],
    max_words: int = 240,
) -> dict | None:
    if not semantic_index or not semantic_index.get("words"):
        return semantic_index

    words = semantic_index.get("words", [])

    def _token_match(text: str) -> bool:
        compact = "".join(ch for ch in text.lower() if ch.isalnum())
        return any(t in compact for t in query_tokens if t)

    def _is_numeric(text: str) -> bool:
        return any(ch.isdigit() for ch in text)

    important_roles = {
        "detail_title", "dimension", "material_spec", "reference",
        "schedule_title", "column_header", "cell_value", "label", "callout",
        "sheet_number",
    }
    important_regions = {"schedule", "notes", "detail", "title_block"}

    filtered = []
    for w in words:
        text = w.get("text") or ""
        role = (w.get("role") or "").lower()
        region = (w.get("region_type") or "").lower()
        if _token_match(text) or _is_numeric(text) or role in important_roles or region in important_regions:
            filtered.append({
                "id": w.get("id"),
                "text": text,
                "bbox": w.get("bbox"),
                "role": w.get("role"),
                "region_type": w.get("region_type"),
            })

    # Keep deterministic order by bbox position if available
    def _sort_key(word: dict) -> tuple:
        bbox = word.get("bbox") or {}
        return (bbox.get("y0", 0), bbox.get("x0", 0))

    filtered.sort(key=_sort_key)
    if len(filtered) > max_words:
        filtered = filtered[:max_words]

    return {
        "image_width": semantic_index.get("image_width"),
        "image_height": semantic_index.get("image_height"),
        "word_count": len(filtered),
        "words": filtered,
    }


def _filter_details(details: list[dict] | None, query_tokens: list[str], max_details: int = 12) -> list[dict]:
    if not details:
        return []

    def _matches(detail: dict) -> bool:
        haystack = " ".join(
            str(detail.get(field) or "") for field in ("title", "number", "shows", "notes")
        ).lower()
        return any(token in haystack for token in query_tokens)

    matched = [d for d in details if _matches(d)]
    if not matched:
        matched = details

    return matched[:max_details]


def _load_page_details_map(db: Session, page_ids: list[str]) -> dict[str, list[dict]]:
    if not page_ids:
        return {}
    pages = (
        db.query(Page)
        .filter(Page.id.in_(page_ids))
        .all()
    )
    return {str(p.id): (p.details or []) for p in pages}


def _load_pages_for_vision(db: Session, page_ids: list[str]) -> list[Page]:
    if not page_ids:
        return []
    pages = (
        db.query(Page)
        .options(joinedload(Page.discipline))
        .filter(Page.id.in_(page_ids))
        .all()
    )
    return pages


def _extract_cross_reference_sheet_names(cross_references: Any) -> set[str]:
    if not isinstance(cross_references, list):
        return set()
    names: set[str] = set()
    for ref in cross_references:
        if isinstance(ref, str):
            sheet_name = ref.strip()
        elif isinstance(ref, dict):
            sheet_name = str(ref.get("sheet") or "").strip()
        else:
            sheet_name = ""
        if sheet_name:
            names.add(sheet_name)
    return names


def _expand_with_cross_reference_pages(
    db: Session,
    project_id: str,
    page_ids: list[str],
    *,
    seed_limit: int = CROSS_REF_PAGE_LIMIT,
    expansion_limit: int = CROSS_REF_PAGE_LIMIT,
) -> list[str]:
    """Add a few cross-referenced pages to improve navigation context."""
    if not page_ids:
        return []

    pages_for_cross_refs = _load_pages_for_vision(db, page_ids[:seed_limit])
    cross_ref_sheet_names: set[str] = set()
    for page in pages_for_cross_refs:
        cross_ref_sheet_names.update(_extract_cross_reference_sheet_names(page.cross_references))

    if not cross_ref_sheet_names:
        return page_ids

    cross_ref_pages = (
        db.query(Page)
        .join(Discipline)
        .filter(
            Discipline.project_id == project_id,
            Page.page_name.in_(list(cross_ref_sheet_names)),
        )
        .order_by(Page.page_name)
        .limit(expansion_limit)
        .all()
    )
    cross_ref_ids = [str(p.id) for p in cross_ref_pages]
    return page_ids + [pid for pid in cross_ref_ids if pid not in page_ids]


def _order_page_ids(
    db: Session,
    page_ids: list[str],
    *,
    sort_by_sheet_number: bool = True,
) -> tuple[list[str], dict[str, Page]]:
    """Sort selected pages by sheet number and return a lookup map."""
    if not page_ids:
        return [], {}

    pages_for_order = _load_pages_for_vision(db, page_ids)
    page_map = {str(p.id): p for p in pages_for_order}
    if sort_by_sheet_number:
        ordered_page_ids = sorted(
            [pid for pid in page_ids if pid in page_map],
            key=lambda pid: _page_sort_key(page_map[pid].page_name or ""),
        )
    else:
        ordered_page_ids = [pid for pid in page_ids if pid in page_map]
    return ordered_page_ids, page_map


async def _load_page_image_bytes(page: Page) -> bytes | None:
    """Load a rendered page image (PNG preferred, PDF fallback)."""
    from app.services.providers.pdf_renderer import pdf_page_to_image
    from app.services.utils.storage import download_file

    try:
        if page.page_image_path and str(page.page_image_path).lower().endswith(".png"):
            return await download_file(page.page_image_path)
        if page.file_path and str(page.file_path).lower().endswith(".pdf"):
            pdf_bytes = await download_file(page.file_path)
            return pdf_page_to_image(pdf_bytes, page.page_index, dpi=150)
        if page.file_path and str(page.file_path).lower().endswith(".png"):
            return await download_file(page.file_path)
    except Exception as e:
        logger.warning("Failed to load page image for %s: %s", page.page_name, e)
    return None


# Tool definitions in OpenAI format
# Note: project_id is injected by execute_tool(), not exposed to the model
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_pointers",
            "description": "Search for relevant pointers (detailed annotations on pages) by keyword/semantic query. Returns pointers with their page info. Use this to find specific details, callouts, or annotations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "discipline": {
                        "type": "string",
                        "description": "Optional discipline filter (e.g., 'Electrical', 'Mechanical')",
                    },
                    "limit": {"type": "integer", "description": "Max results (default 10)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_pages",
            "description": "Search for pages/sheets by name or content. Use this to find specific sheets (e.g., 'E-2.1', 'panel schedule') or pages containing certain content. Returns page names with context snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (matches page name or context)"},
                    "discipline": {
                        "type": "string",
                        "description": "Optional discipline filter (e.g., 'Electrical', 'Mechanical')",
                    },
                    "limit": {"type": "integer", "description": "Max results (default 10)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pointer",
            "description": "Get full details of a specific pointer including its description, text content, and references to other pages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pointer_id": {"type": "string", "description": "Pointer UUID"}
                },
                "required": ["pointer_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_page_context",
            "description": "Get summary of a page and all pointers on it. Use to understand what's on a specific page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "Page UUID"}
                },
                "required": ["page_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_discipline_overview",
            "description": "Get high-level view of a discipline including all pages and cross-references to other disciplines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "discipline_id": {"type": "string", "description": "Discipline UUID"}
                },
                "required": ["discipline_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_project_pages",
            "description": "List all pages in the project organized by discipline. Use to understand project structure.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_references_to_page",
            "description": "Find all pointers that reference a specific page (reverse lookup). Use to discover what points TO a page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "Page UUID"}
                },
                "required": ["page_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select_pages",
            "description": "Display specific pages in the plan viewer for the user to see. Use this when the user asks to see specific pages or when you want to show them relevant plan sheets. Pages will be displayed without any pointer highlighting.",
            "parameters": {
                "type": "object",
                "properties": {
                    "page_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of page UUIDs to display",
                    }
                },
                "required": ["page_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select_pointers",
            "description": "Highlight specific pointers on the plan viewer to show the user which areas of the plans are relevant to their query. This also displays the pages containing those pointers. Use when you want to highlight specific details on the plans.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pointer_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of pointer UUIDs to highlight",
                    }
                },
                "required": ["pointer_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_display_title",
            "description": "Set titles for this chat and the overall conversation. Call this ONCE before your final answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_title": {
                        "type": "string",
                        "description": "2-4 word noun phrase for THIS query (e.g., 'Electrical Panels', 'Kitchen Equipment')",
                    },
                    "conversation_title": {
                        "type": "string",
                        "description": "2-6 word phrase summarizing the ENTIRE conversation so far",
                    }
                },
                "required": ["chat_title", "conversation_title"],
            },
        },
    },
]

AGENT_SYSTEM_PROMPT = """You are a construction plan analysis agent. You help superintendents find information across construction documents by navigating a graph of pages and details (pointers).

You have access to these tools:
- search_pointers: Find relevant pointers (annotations/details) by keyword/semantic search
- search_pages: Find pages/sheets by name or content (e.g., "E-2.1", "panel schedule")
- get_pointer: Get full details of a specific pointer including references to other pages
- get_page_context: Get summary of a page and all pointers on it
- get_discipline_overview: Get high-level view of a discipline (architectural, structural, etc.)
- list_project_pages: See all pages in the project
- get_references_to_page: Find what points TO a specific page (reverse lookup)
- select_pages: Display specific pages in the plan viewer for the user to see
- select_pointers: Highlight specific pointers on pages to show the user relevant areas
- set_display_title: Set a short title for this query (REQUIRED before final answer)

STRATEGY - SEARCH RESULTS ARE PRE-FETCHED:

Search results for both pages and pointers have ALREADY been fetched and are provided below.
DO NOT call search_pages or search_pointers - the results are already here.

YOUR JOB:
1. Review the pre-fetched results below
2. Decide which pages/pointers to display
3. Call select_pages and/or select_pointers with the relevant IDs
4. Call set_display_title
5. Write a brief response

WHEN TO USE ADDITIONAL TOOLS (escape hatch):
- If the pre-fetched results are empty or unhelpful, you MAY call search_pages/search_pointers with different terms
- If you need detailed pointer info, you MAY call get_pointer or get_page_context
- But for most queries, the pre-fetched results are sufficient - just select and respond

EFFICIENCY IS CRITICAL:
- Most queries should complete in ONE tool call batch: select_pages + set_display_title
- Superintendents are on job sites. Every second counts.

DISPLAYING RESULTS - SHOW ALL RELEVANT PAGES:
- Your goal is to show the user ALL pages relevant to their question, not just pages with pointers.
- Use select_pointers for pages where you found specific relevant pointers to highlight
- Use select_pages for pages that are relevant but don't have specific pointers to highlight
- You CAN call BOTH tools in the same query! For example: if 2 pages have relevant pointers and 3 more pages are relevant but have no pointers, call select_pointers for the 2 AND select_pages for the 3.
- IMPORTANT: Pages without pointers can still be highly relevant. Don't skip them just because there's nothing to highlight.
- PAGE ORDERING: Order pages numerically by sheet number (e.g., E-2.1, E-2.2, E-2.3). If the user requests a specific order, follow their preference instead.
- Always call at least one of these tools before your final answer so the user can see the relevant plans.

BEFORE YOUR FINAL ANSWER:
- Call set_display_title with:
  - chat_title: 2-4 word noun phrase for THIS question (e.g., "Electrical Panels", "Kitchen Equipment")
  - conversation_title: 2-6 word phrase summarizing ALL topics discussed in this conversation
    - First query: same as chat_title
    - Follow-ups: combine themes (e.g., "Kitchen & Electrical Plans", "Panel Details and Locations")

RESPONSE STYLE:
You're a helpful secondary superintendent - knowledgeable, casual, and to the point. Talk like a colleague, not a robot.

DO:
- Sound natural: "Got your kitchen equipment plans - K-201 is the overview, the other two are enlarged sections."
- Add useful context: "Panel schedule's on E-3.2, but you'll want E-3.1 too for the one-line diagram."
- Be brief: 1-2 sentences max. Superintendents are busy.

DON'T:
- Announce what you did: "I have displayed the pages" ❌
- Sound robotic: "The requested documents are now shown" ❌
- List things formally: "These are: K-212, K-201, K-211" ❌
- Repeat what the user asked for: "You asked about equipment floor plans and I found equipment floor plans" ❌

THINKING OUT LOUD (during tool calls only):
- Verbalize your reasoning BEFORE each tool call: "Let me check the kitchen sheets...", "Found a few options, looking at the first one..."
- Brief status updates help the user follow along

FINAL ANSWER (after all tools are done):
- Jump straight into your response - NO preamble, NO reasoning, NO "let me now..."
- Your final answer should start with the actual information, not with what you're about to do
- WRONG: "Good, I found the pages. Now let me give you a brief answer. K-201 is your overview..."
- RIGHT: "K-201 is your overview, with K-211 and K-212 showing the enlarged sections."
- The user sees your tool calls, so don't narrate what just happened

CONVERSATION CONTEXT:
If there are previous messages in this conversation, use that context to:
- Understand pronouns and references (e.g., "those panels", "the second one", "what about floor 2?")
- Avoid repeating searches you've already done unless the user asks for fresh results
- Build on previous findings rather than starting from scratch
- Remember what pages/pointers you've already shown"""


async def execute_tool(
    db: Session,
    project_id: str,
    tool_name: str,
    tool_input: dict,
) -> dict:
    """Execute a tool and return JSON-serializable result."""
    from app.services.tools import TOOL_REGISTRY

    tool_fn = TOOL_REGISTRY.get(tool_name)
    if not tool_fn:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        # Inject project_id for tools that need it
        if tool_name in ("search_pointers", "search_pages"):
            result = await tool_fn(db, project_id=project_id, **tool_input)
        elif tool_name == "list_project_pages":
            result = await tool_fn(db, project_id=project_id)
        elif tool_name in ("select_pages", "select_pointers"):
            result = await tool_fn(db, **tool_input)
        else:
            result = await tool_fn(db, **tool_input)

        # Convert Pydantic model to dict
        if hasattr(result, "model_dump"):
            return result.model_dump(by_alias=True, mode="json")
        # search_pointers returns list[dict], not a Pydantic model
        # Use `is not None` to allow empty lists [] as valid results
        return result if result is not None else {"error": "Not found"}
    except Exception as e:
        logger.exception(f"Tool execution error for {tool_name}: {e}")
        return {"error": str(e)}


async def run_agent_query(
    db: Session,
    project_id: str,
    query: str,
    history_messages: list[dict[str, Any]] | None = None,
    viewing_context: dict[str, Any] | None = None,
    mode: Literal["fast", "med", "deep"] = "fast",
) -> AsyncIterator[dict]:
    """
    Execute agent query with streaming events.

    Modes:
    - fast (default): RAG + project structure routing (no vision calls)
    - med: fast-style page routing + deterministic region highlights (no vision calls)
    - deep: RAG + agentic vision exploration with streamed thinking

    Backend selection:
    - AGENT_BACKEND=grok is only used for fast mode
    - Deep mode always uses Gemini vision exploration

    Yields events:
    - {"type": "text", "content": "..."} - Model's reasoning/response
    - {"type": "tool_call", "tool": "...", "input": {...}} - Tool being called
    - {"type": "tool_result", "tool": "...", "result": {...}} - Tool result
    - {"type": "done", "trace": [...], "usage": {...}, "displayTitle": "..."} - Final event

    Args:
        db: Database session
        project_id: Project UUID (injected into tools that need it)
        query: User's question
        history_messages: Optional list of previous messages in conversation
        viewing_context: Optional dict with page_id, page_name, discipline_name if user is viewing a page
        mode: "fast", "med", or "deep"
    """
    settings = get_settings()
    mode = "deep" if mode == "deep" else "med" if mode == "med" else "fast"
    if mode == "med" and not bool(getattr(settings, "med_mode_regions", False)):
        logger.info("Med mode requested but MED_MODE_REGIONS is disabled; falling back to fast mode.")
        mode = "fast"
    backend = os.environ.get("AGENT_BACKEND", "gemini").lower()

    if mode == "deep":
        async for event in run_agent_query_deep(
            db, project_id, query, history_messages, viewing_context
        ):
            yield event
    elif mode == "med":
        async for event in run_agent_query_med(
            db, project_id, query, history_messages, viewing_context
        ):
            yield event
    elif backend == "grok":
        async for event in run_agent_query_grok(db, project_id, query, history_messages, viewing_context):
            yield event
    else:
        async for event in run_agent_query_fast(db, project_id, query, history_messages, viewing_context):
            yield event


async def run_agent_query_fast(
    db: Session,
    project_id: str,
    query: str,
    history_messages: list[dict[str, Any]] | None = None,
    viewing_context: dict[str, Any] | None = None,
) -> AsyncIterator[dict]:
    """
    Fast mode:
    - Pull project structure summary
    - Use RAG to identify candidate pages
    - Let Gemini Flash select the most relevant pages with concise reasoning
    - Route user to those pages without running vision inference
    """
    from app.services.providers.gemini import route_fast_query, select_pages_smart
    from app.services.tools import get_project_structure_summary, search_pages, select_pages
    from app.services.utils.search import search_pages_and_regions

    trace: list[dict] = []
    history_context = _build_history_context(history_messages)
    viewing_context_str = _build_viewing_context_str(viewing_context)
    # Extract memory_context if passed through viewing_context (from Big Maestro)
    memory_context = ""
    if viewing_context and isinstance(viewing_context, dict):
        memory_context = viewing_context.get("memory_context", "")
    page_navigation_intent = _is_page_navigation_query(query)
    settings = get_settings()
    fast_ranker_v2 = bool(getattr(settings, "fast_ranker_v2", False))
    fast_selector_rerank = bool(getattr(settings, "fast_selector_rerank", False))
    should_run_selector = (not fast_ranker_v2) or fast_selector_rerank

    # 0) Lightweight query router to steer retrieval before smart selection.
    yield {"type": "tool_call", "tool": "route_fast_query", "input": {"query": query}}
    trace.append({"type": "tool_call", "tool": "route_fast_query", "input": {"query": query}})
    router: dict[str, Any] = {
        "intent": "page_navigation" if page_navigation_intent else "qa",
        "must_terms": [],
        "preferred_page_types": [],
        "strict": False,
        "k": FAST_PAGE_LIMIT,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }
    try:
        router = await route_fast_query(
            query=query,
            history_context=history_context,
            viewing_context=viewing_context_str,
            memory_context=memory_context,
        )
    except Exception as e:
        logger.warning("route_fast_query failed, continuing with defaults: %s", e)

    router_result = router if isinstance(router, dict) else {}
    yield {"type": "tool_result", "tool": "route_fast_query", "result": router_result}
    trace.append({"type": "tool_result", "tool": "route_fast_query", "result": router_result})

    router_intent = str(router_result.get("intent") or "").strip().lower()
    if router_intent == "page_navigation":
        page_navigation_intent = True
    router_must_terms = _normalize_router_terms(router_result.get("must_terms"))
    router_preferred_page_types = _normalize_router_page_types(router_result.get("preferred_page_types"))
    router_preferred_disciplines = _infer_preferred_disciplines(query, router_must_terms)
    router_area_or_level = _infer_area_or_level(query)
    router_focus = _infer_focus(query, router_must_terms)
    router_model = str(router_result.get("model") or "").strip() or "fallback"
    router_strict = _to_bool(router_result.get("strict"), default=False) and page_navigation_intent
    router_k = FAST_PAGE_LIMIT
    try:
        router_k = int(router_result.get("k"))
    except (TypeError, ValueError):
        router_k = FAST_PAGE_LIMIT
    router_k = max(1, min(FAST_PAGE_LIMIT, router_k))
    target_page_limit = router_k
    search_query = _build_routed_search_query(query, router_must_terms, router_preferred_page_types)

    # 1) Load project structure summary for context
    yield {"type": "tool_call", "tool": "list_project_pages", "input": {}}
    trace.append({"type": "tool_call", "tool": "list_project_pages", "input": {}})

    project_structure: dict[str, Any] = {"disciplines": [], "total_pages": 0}
    try:
        structure_result = await get_project_structure_summary(db, project_id=project_id)
        if isinstance(structure_result, dict):
            project_structure = structure_result
    except Exception as e:
        logger.warning("Project structure summary failed: %s", e)

    yield {"type": "tool_result", "tool": "list_project_pages", "result": project_structure}
    trace.append({"type": "tool_result", "tool": "list_project_pages", "result": project_structure})

    # 2) RAG search by regions
    yield {
        "type": "tool_call",
        "tool": "search_pages_and_regions",
        "input": {"query": search_query, "source_query": query},
    }
    trace.append(
        {
            "type": "tool_call",
            "tool": "search_pages_and_regions",
            "input": {"query": search_query, "source_query": query},
        }
    )

    try:
        region_matches = await search_pages_and_regions(db, query=search_query, project_id=project_id)
    except Exception as e:
        logger.exception("Region search failed: %s", e)
        yield {"type": "error", "message": f"Search failed: {str(e)}"}
        return

    yield {"type": "tool_result", "tool": "search_pages_and_regions", "result": region_matches}
    trace.append({"type": "tool_result", "tool": "search_pages_and_regions", "result": region_matches})

    # 3) Secondary keyword search to improve routing confidence
    yield {
        "type": "tool_call",
        "tool": "search_pages",
        "input": {"query": search_query, "source_query": query},
    }
    trace.append(
        {
            "type": "tool_call",
            "tool": "search_pages",
            "input": {"query": search_query, "source_query": query},
        }
    )
    page_results = await search_pages(db, query=search_query, project_id=project_id, limit=FAST_PAGE_LIMIT)
    yield {"type": "tool_result", "tool": "search_pages", "result": page_results}
    trace.append({"type": "tool_result", "tool": "search_pages", "result": page_results})
    for page_result in page_results:
        if isinstance(page_result, dict):
            _hydrate_sheet_card(page_result)
    exact_title_page_ids = _select_exact_title_hits(query, router_must_terms, page_results)

    strict_page_matches: list[dict[str, Any]] = []
    if router_strict:
        strict_page_matches = _filter_pages_for_router(
            page_results,
            router_must_terms,
            router_preferred_page_types,
        )

    selection_candidates = page_results
    if strict_page_matches:
        selection_candidates = strict_page_matches[: max(3, target_page_limit)]

    # 4) Optional LLM page selection over compact candidates (can be skipped in FAST_RANKER_V2 mode).
    selection_input = {
        "query": query,
        "routed_query": search_query,
        "router": {
            "intent": router_intent or ("page_navigation" if page_navigation_intent else "qa"),
            "focus": router_focus,
            "must_terms": router_must_terms,
            "preferred_disciplines": router_preferred_disciplines,
            "preferred_page_types": router_preferred_page_types,
            "area_or_level": router_area_or_level,
            "strict": router_strict,
            "k": target_page_limit,
            "model": router_model,
        },
        "candidate_page_ids": [
            p.get("page_id")
            for p in selection_candidates
            if isinstance(p, dict) and p.get("page_id")
        ],
        "project_page_count": project_structure.get("total_pages", 0),
    }

    selection: dict[str, Any] = {}
    selection_result: dict[str, Any]
    if should_run_selector:
        yield {"type": "tool_call", "tool": "select_pages_smart", "input": selection_input}
        trace.append({"type": "tool_call", "tool": "select_pages_smart", "input": selection_input})
        try:
            selection = await select_pages_smart(
                project_structure=project_structure,
                page_candidates=selection_candidates,
                query=query,
                history_context=history_context,
                viewing_context=viewing_context_str,
                memory_context=memory_context,
            )
            selection_result = selection
        except Exception as e:
            logger.warning("Smart page selection failed, falling back to deterministic routing: %s", e)
            selection_result = {
                "error": str(e),
                "selected_pages": [],
                "chat_title": None,
                "conversation_title": None,
                "response": "",
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
    else:
        selection_result = {
            "selected_pages": [],
            "page_ids": [],
            "chat_title": None,
            "conversation_title": None,
            "response": "",
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "skipped": True,
            "reason": "FAST_RANKER_V2 deterministic ranking",
        }

    yield {"type": "tool_result", "tool": "select_pages_smart", "result": selection_result}
    trace.append({"type": "tool_result", "tool": "select_pages_smart", "result": selection_result})

    selected_page_ids: list[str] = []
    raw_selected_pages = selection.get("selected_pages")
    selector_relevance_by_id: dict[str, str] = {}
    if isinstance(raw_selected_pages, list):
        for item in raw_selected_pages:
            if not isinstance(item, dict):
                continue
            page_id = str(item.get("page_id") or "").strip()
            if page_id:
                selected_page_ids.append(page_id)
                relevance_text = str(item.get("relevance") or "").strip()
                if relevance_text and page_id not in selector_relevance_by_id:
                    selector_relevance_by_id[page_id] = relevance_text

    if not selected_page_ids:
        raw_page_ids = selection.get("page_ids")
        if isinstance(raw_page_ids, list):
            for item in raw_page_ids:
                page_id = str(item).strip()
                if page_id:
                    selected_page_ids.append(page_id)

    vector_page_ids = _dedupe_ids([pid for pid in region_matches.keys() if pid], limit=FAST_PAGE_LIMIT)
    region_page_ids = list(vector_page_ids)
    keyword_page_ids = _dedupe_ids(
        [str(p.get("page_id")) for p in page_results if isinstance(p, dict) and p.get("page_id")],
        limit=FAST_PAGE_LIMIT,
    )
    selected_page_ids = _dedupe_ids(selected_page_ids, limit=FAST_PAGE_LIMIT)
    strict_keyword_page_ids = [
        p.get("page_id")
        for p in strict_page_matches
        if isinstance(p, dict) and p.get("page_id")
    ]
    strict_keyword_page_ids = _dedupe_ids([str(pid) for pid in strict_keyword_page_ids], limit=FAST_PAGE_LIMIT)
    tree_page_ids: list[str] = []

    if router_strict and strict_keyword_page_ids:
        strict_id_set = set(strict_keyword_page_ids)
        selected_page_ids = [pid for pid in selected_page_ids if pid in strict_id_set]
        region_page_ids = [pid for pid in region_page_ids if pid in strict_id_set]

    if page_navigation_intent:
        tree_page_ids = _select_project_tree_page_ids(project_structure, query, max(target_page_limit, 6))

    page_lookup = _build_project_structure_page_lookup(project_structure)
    for page_result in page_results:
        if not isinstance(page_result, dict):
            continue
        page_id = str(page_result.get("page_id") or "").strip()
        if not page_id:
            continue
        entry = page_lookup.setdefault(page_id, {})
        sheet_card = page_result.get("sheet_card")
        if not isinstance(sheet_card, dict):
            sheet_card = _hydrate_sheet_card(page_result)
        entry.update(
            {
                "page_name": str(page_result.get("page_name") or entry.get("page_name") or "").strip(),
                "discipline": str(page_result.get("discipline") or entry.get("discipline") or "").strip(),
                "page_type": str(page_result.get("page_type") or entry.get("page_type") or "").strip(),
                "content": str(page_result.get("content") or entry.get("content") or "").strip(),
                "sheet_card": sheet_card,
            }
        )

    source_hit_sets = {
        "exact_title_hits": set(exact_title_page_ids),
        "reflection_keyword_hits": set(keyword_page_ids),
        "vector_hits": set(vector_page_ids),
        "region_hits": set(region_page_ids),
        "project_tree_hits": set(tree_page_ids),
        "strict_keyword_hits": set(strict_keyword_page_ids),
        "smart_selector_hits": set(selected_page_ids),
    }

    if fast_ranker_v2:
        candidate_pool = _dedupe_ids(
            [
                *exact_title_page_ids,
                *strict_keyword_page_ids,
                *keyword_page_ids,
                *region_page_ids,
                *vector_page_ids,
                *selected_page_ids,
                *tree_page_ids,
            ]
        )
        if router_strict and strict_keyword_page_ids:
            strict_set = set(strict_keyword_page_ids)
            exact_set = set(exact_title_page_ids)
            candidate_pool = [pid for pid in candidate_pool if pid in strict_set or pid in exact_set]
            if not candidate_pool:
                candidate_pool = _dedupe_ids([*strict_keyword_page_ids, *exact_title_page_ids])

        if not candidate_pool:
            candidate_pool = _select_cover_index_fallback_page_ids(
                project_structure,
                max(target_page_limit, 6),
            )

        page_ids = _rank_candidate_page_ids_v2(
            candidate_pool,
            page_lookup=page_lookup,
            query=query,
            must_terms=router_must_terms,
            preferred_page_types=router_preferred_page_types,
            preferred_disciplines=router_preferred_disciplines,
            area_or_level=router_area_or_level,
            entity_terms=_extract_entity_terms(query),
            vector_hits=vector_page_ids,
            source_hit_sets=source_hit_sets,
            limit=max(target_page_limit, 6),
        )
    else:
        if page_navigation_intent:
            if router_strict and strict_keyword_page_ids:
                primary_ids = list(
                    dict.fromkeys([*strict_keyword_page_ids, *region_page_ids, *selected_page_ids])
                )
                fallback_pool = [
                    pid
                    for pid in [*tree_page_ids, *keyword_page_ids]
                    if pid and pid not in primary_ids
                ]
                fallback_budget = max(0, min(2, target_page_limit - len(primary_ids)))
                page_ids = primary_ids + fallback_pool[:fallback_budget]
            else:
                page_ids = list(dict.fromkeys([*keyword_page_ids, *region_page_ids, *selected_page_ids, *tree_page_ids]))
        elif selected_page_ids:
            page_ids = list(dict.fromkeys(selected_page_ids))
        else:
            page_ids = list(dict.fromkeys([*region_page_ids, *keyword_page_ids]))

    if not page_ids:
        page_ids = _select_cover_index_fallback_page_ids(project_structure, target_page_limit)

    if not page_ids:
        # Last-resort fallback: choose a few sheets from project structure.
        disciplines = project_structure.get("disciplines", [])
        if isinstance(disciplines, list):
            for discipline in disciplines:
                pages = discipline.get("pages", []) if isinstance(discipline, dict) else []
                if not isinstance(pages, list):
                    continue
                for page in pages:
                    if not isinstance(page, dict):
                        continue
                    page_id = page.get("page_id")
                    if page_id and page_id not in page_ids:
                        page_ids.append(page_id)
                    if len(page_ids) >= target_page_limit:
                        break
                if len(page_ids) >= target_page_limit:
                    break

    page_ids_before_cross_refs = list(dict.fromkeys(page_ids))
    cross_reference_page_ids: set[str] = set()
    if page_ids:
        page_ids = _expand_with_cross_reference_pages(db, project_id, page_ids)
        cross_reference_page_ids = set(page_ids) - set(page_ids_before_cross_refs)

    page_ids = list(dict.fromkeys([pid for pid in page_ids if pid]))[:target_page_limit]
    ordered_page_ids, page_map = _order_page_ids(
        db,
        page_ids,
        sort_by_sheet_number=not fast_ranker_v2,
    )

    query_plan = {
        "intent": router_intent or ("page_navigation" if page_navigation_intent else "qa"),
        "focus": router_focus or None,
        "must_terms": router_must_terms,
        "preferred_disciplines": router_preferred_disciplines,
        "preferred_page_types": router_preferred_page_types,
        "area_or_level": router_area_or_level,
        "strict": router_strict,
        "k": target_page_limit,
        "model": router_model,
        "ranker": "v2" if fast_ranker_v2 else "v1",
        "selector_rerank": should_run_selector,
    }
    candidate_sets = {
        "exact_title_hits": _build_candidate_set(exact_title_page_ids),
        "reflection_keyword_hits": _build_candidate_set(keyword_page_ids),
        "vector_hits": _build_candidate_set(vector_page_ids),
        "region_hits": _build_candidate_set(region_page_ids),
        "project_tree_hits": _build_candidate_set(tree_page_ids),
        "strict_keyword_hits": _build_candidate_set(strict_keyword_page_ids),
        "smart_selector_hits": _build_candidate_set(selected_page_ids),
    }

    for page_id, page_obj in page_map.items():
        entry = page_lookup.setdefault(page_id, {})
        page_name = getattr(page_obj, "page_name", None)
        if page_name:
            entry["page_name"] = page_name
        page_type = getattr(page_obj, "page_type", None)
        if page_type and not entry.get("page_type"):
            entry["page_type"] = page_type
        discipline_obj = getattr(page_obj, "discipline", None)
        discipline_name = getattr(discipline_obj, "display_name", None) if discipline_obj else None
        if discipline_name and not entry.get("discipline"):
            entry["discipline"] = discipline_name
        existing_sheet_card = entry.get("sheet_card")
        if not isinstance(existing_sheet_card, dict) or not existing_sheet_card:
            stored_sheet_card = getattr(page_obj, "sheet_card", None)
            if isinstance(stored_sheet_card, dict) and stored_sheet_card:
                entry["sheet_card"] = stored_sheet_card
            else:
                entry["sheet_card"] = build_sheet_card(
                    sheet_number=getattr(page_obj, "page_name", None),
                    page_type=getattr(page_obj, "page_type", None),
                    discipline_name=discipline_name,
                    sheet_reflection=getattr(page_obj, "sheet_reflection", None),
                    master_index=(
                        page_obj.master_index
                        if isinstance(getattr(page_obj, "master_index", None), dict)
                        else None
                    ),
                    keywords=None,
                    cross_references=getattr(page_obj, "cross_references", None),
                )

    source_hit_sets = {
        "exact_title_hits": set(candidate_sets["exact_title_hits"]["top_ids"]),
        "reflection_keyword_hits": set(candidate_sets["reflection_keyword_hits"]["top_ids"]),
        "vector_hits": set(candidate_sets["vector_hits"]["top_ids"]),
        "region_hits": set(candidate_sets["region_hits"]["top_ids"]),
        "project_tree_hits": set(candidate_sets["project_tree_hits"]["top_ids"]),
        "strict_keyword_hits": set(candidate_sets["strict_keyword_hits"]["top_ids"]),
        "smart_selector_hits": set(candidate_sets["smart_selector_hits"]["top_ids"]),
    }
    rank_breakdown = _build_rank_breakdown(
        query=query,
        ordered_page_ids=ordered_page_ids,
        page_lookup=page_lookup,
        must_terms=router_must_terms,
        preferred_page_types=router_preferred_page_types,
        preferred_disciplines=router_preferred_disciplines,
        area_or_level=router_area_or_level,
        entity_terms=_extract_entity_terms(query),
        vector_hits=vector_page_ids,
        source_hit_sets=source_hit_sets,
    )
    final_selection = _build_final_selection_trace(
        ordered_page_ids=ordered_page_ids,
        page_lookup=page_lookup,
        target_page_limit=target_page_limit,
        page_navigation_intent=page_navigation_intent,
        source_hit_sets=source_hit_sets,
        selector_relevance_by_id=selector_relevance_by_id,
        cross_reference_page_ids=cross_reference_page_ids,
    )

    router_usage_raw = router_result.get("usage") if isinstance(router_result.get("usage"), dict) else {}
    selector_usage_raw = (
        selection_result.get("usage")
        if isinstance(selection_result.get("usage"), dict)
        else {}
    )
    router_input_tokens = _coerce_int(router_usage_raw.get("input_tokens") or router_usage_raw.get("inputTokens"))
    router_output_tokens = _coerce_int(router_usage_raw.get("output_tokens") or router_usage_raw.get("outputTokens"))
    selector_input_tokens = _coerce_int(selector_usage_raw.get("input_tokens") or selector_usage_raw.get("inputTokens"))
    selector_output_tokens = _coerce_int(selector_usage_raw.get("output_tokens") or selector_usage_raw.get("outputTokens"))
    token_cost = {
        "router": {
            "input_tokens": router_input_tokens,
            "output_tokens": router_output_tokens,
        },
        "selector": {
            "input_tokens": selector_input_tokens,
            "output_tokens": selector_output_tokens,
        },
        "total": {
            "input_tokens": router_input_tokens + selector_input_tokens,
            "output_tokens": router_output_tokens + selector_output_tokens,
        },
    }

    fast_mode_trace_payload = {
        "query_plan": query_plan,
        "candidate_sets": candidate_sets,
        "rank_breakdown": rank_breakdown,
        "final_selection": final_selection,
        "token_cost": token_cost,
    }
    yield {"type": "tool_result", "tool": "fast_mode_trace", "result": fast_mode_trace_payload}
    trace.append({"type": "tool_result", "tool": "fast_mode_trace", "result": fast_mode_trace_payload})

    # 5) Select pages for frontend display
    if ordered_page_ids:
        yield {"type": "tool_call", "tool": "select_pages", "input": {"page_ids": ordered_page_ids}}
        trace.append({"type": "tool_call", "tool": "select_pages", "input": {"page_ids": ordered_page_ids}})
        try:
            result = await select_pages(db, page_ids=ordered_page_ids)
            if hasattr(result, "model_dump"):
                result = result.model_dump(by_alias=True, mode="json")
            yield {"type": "tool_result", "tool": "select_pages", "result": result}
            trace.append({"type": "tool_result", "tool": "select_pages", "result": result})
        except Exception as e:
            logger.error(f"select_pages failed: {e}")
            error_result = {"error": str(e)}
            yield {"type": "tool_result", "tool": "select_pages", "result": error_result}
            trace.append({"type": "tool_result", "tool": "select_pages", "result": error_result})

    # 6) Compose response text
    response_text = ""
    if page_navigation_intent and ordered_page_ids:
        top_names = [
            page_map[pid].page_name
            for pid in ordered_page_ids[:4]
            if pid in page_map and page_map[pid].page_name
        ]
        if top_names:
            response_text = f"Showing likely sheets: {', '.join(top_names)}."
            if len(ordered_page_ids) > len(top_names):
                response_text += f" I also pulled {len(ordered_page_ids) - len(top_names)} related sheets."
        else:
            response_text = f"Pulled {len(ordered_page_ids)} relevant sheets for review."
    else:
        response_text = selection.get("response") if isinstance(selection.get("response"), str) else ""
        response_text = response_text.strip()

    if not response_text and ordered_page_ids:
        top_names = [
            page_map[pid].page_name
            for pid in ordered_page_ids[:4]
            if pid in page_map and page_map[pid].page_name
        ]
        if top_names:
            response_text = f"Best sheets to check first: {', '.join(top_names)}."
            if len(ordered_page_ids) > len(top_names):
                response_text += f" I also pulled {len(ordered_page_ids) - len(top_names)} related sheets."
        else:
            response_text = f"Pulled {len(ordered_page_ids)} relevant sheets for review."
    elif not response_text:
        response_text = "I couldn't find a strong page match yet. Try adding a sheet number or discipline keyword."

    if response_text:
        yield {"type": "text", "content": response_text}
        trace.append({"type": "reasoning", "content": response_text})

    input_tokens = token_cost["total"]["input_tokens"]
    output_tokens = token_cost["total"]["output_tokens"]

    tokens = _extract_query_tokens(query)
    fallback_title = " ".join(tokens[:3]).title() if tokens else "Query"
    display_title = str(selection.get("chat_title") or "").strip() or fallback_title
    conversation_title = str(selection.get("conversation_title") or "").strip() or display_title

    yield {
        "type": "done",
        "trace": trace,
        "usage": {"inputTokens": input_tokens, "outputTokens": output_tokens},
        "displayTitle": display_title,
        "conversationTitle": conversation_title,
        "highlights": [],
        "conceptName": None,
        "summary": None,
        "findings": [],
        "crossReferences": [],
        "gaps": [],
    }


async def run_agent_query_med(
    db: Session,
    project_id: str,
    query: str,
    history_messages: list[dict[str, Any]] | None = None,
    viewing_context: dict[str, Any] | None = None,
) -> AsyncIterator[dict]:
    """
    Med mode:
    - Reuses fast-style page retrieval/ranking
    - Deterministically selects likely regions from Brain Mode metadata
    - Resolves region highlights without live vision inference
    """
    from app.services.providers.gemini import route_fast_query, select_pages_smart
    from app.services.tools import (
        get_project_structure_summary,
        resolve_highlights,
        search_pages,
        select_pages,
    )
    from app.services.utils.search import search_pages_and_regions

    trace: list[dict] = []
    history_context = _build_history_context(history_messages)
    viewing_context_str = _build_viewing_context_str(viewing_context)
    # Extract memory_context if passed through viewing_context (from Big Maestro)
    memory_context = ""
    if viewing_context and isinstance(viewing_context, dict):
        memory_context = viewing_context.get("memory_context", "")
    page_navigation_intent = _is_page_navigation_query(query)

    # 0) Query routing (same lightweight router used by fast mode).
    yield {"type": "tool_call", "tool": "route_fast_query", "input": {"query": query}}
    trace.append({"type": "tool_call", "tool": "route_fast_query", "input": {"query": query}})
    router: dict[str, Any] = {
        "intent": "page_navigation" if page_navigation_intent else "qa",
        "must_terms": [],
        "preferred_page_types": [],
        "strict": False,
        "k": MED_PAGE_LIMIT,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }
    try:
        router = await route_fast_query(
            query=query,
            history_context=history_context,
            viewing_context=viewing_context_str,
            memory_context=memory_context,
        )
    except Exception as e:
        logger.warning("route_fast_query failed for med mode, continuing with defaults: %s", e)

    router_result = router if isinstance(router, dict) else {}
    yield {"type": "tool_result", "tool": "route_fast_query", "result": router_result}
    trace.append({"type": "tool_result", "tool": "route_fast_query", "result": router_result})

    router_intent = str(router_result.get("intent") or "").strip().lower()
    if router_intent == "page_navigation":
        page_navigation_intent = True
    router_must_terms = _normalize_router_terms(router_result.get("must_terms"))
    router_preferred_page_types = _normalize_router_page_types(router_result.get("preferred_page_types"))
    router_preferred_disciplines = _infer_preferred_disciplines(query, router_must_terms)
    router_area_or_level = _infer_area_or_level(query)
    router_focus = _infer_focus(query, router_must_terms)
    router_model = str(router_result.get("model") or "").strip() or "fallback"
    router_strict = _to_bool(router_result.get("strict"), default=False) and page_navigation_intent

    router_k = MED_PAGE_LIMIT
    try:
        router_k = int(router_result.get("k"))
    except (TypeError, ValueError):
        router_k = MED_PAGE_LIMIT
    target_page_limit = max(1, min(MED_PAGE_LIMIT, router_k))
    search_query = _build_routed_search_query(query, router_must_terms, router_preferred_page_types)

    # 1) Load project structure summary.
    yield {"type": "tool_call", "tool": "list_project_pages", "input": {}}
    trace.append({"type": "tool_call", "tool": "list_project_pages", "input": {}})

    project_structure: dict[str, Any] = {"disciplines": [], "total_pages": 0}
    try:
        structure_result = await get_project_structure_summary(db, project_id=project_id)
        if isinstance(structure_result, dict):
            project_structure = structure_result
    except Exception as e:
        logger.warning("Project structure summary failed in med mode: %s", e)

    yield {"type": "tool_result", "tool": "list_project_pages", "result": project_structure}
    trace.append({"type": "tool_result", "tool": "list_project_pages", "result": project_structure})

    # 2) Region retrieval lane.
    yield {
        "type": "tool_call",
        "tool": "search_pages_and_regions",
        "input": {"query": search_query, "source_query": query},
    }
    trace.append(
        {
            "type": "tool_call",
            "tool": "search_pages_and_regions",
            "input": {"query": search_query, "source_query": query},
        }
    )
    try:
        region_matches = await search_pages_and_regions(
            db,
            query=search_query,
            project_id=project_id,
            limit=FAST_PAGE_LIMIT,
        )
    except Exception as e:
        logger.exception("Region search failed in med mode: %s", e)
        yield {"type": "error", "message": f"Search failed: {str(e)}"}
        return

    yield {"type": "tool_result", "tool": "search_pages_and_regions", "result": region_matches}
    trace.append({"type": "tool_result", "tool": "search_pages_and_regions", "result": region_matches})

    # 3) Secondary page retrieval lane.
    yield {
        "type": "tool_call",
        "tool": "search_pages",
        "input": {"query": search_query, "source_query": query},
    }
    trace.append(
        {
            "type": "tool_call",
            "tool": "search_pages",
            "input": {"query": search_query, "source_query": query},
        }
    )
    page_results = await search_pages(db, query=search_query, project_id=project_id, limit=FAST_PAGE_LIMIT)
    yield {"type": "tool_result", "tool": "search_pages", "result": page_results}
    trace.append({"type": "tool_result", "tool": "search_pages", "result": page_results})
    for page_result in page_results:
        if isinstance(page_result, dict):
            _hydrate_sheet_card(page_result)

    exact_title_page_ids = _select_exact_title_hits(query, router_must_terms, page_results)

    strict_page_matches: list[dict[str, Any]] = []
    if router_strict:
        strict_page_matches = _filter_pages_for_router(
            page_results,
            router_must_terms,
            router_preferred_page_types,
        )

    selection_candidates = page_results
    if strict_page_matches:
        selection_candidates = strict_page_matches[: max(3, target_page_limit)]

    selection_input = {
        "query": query,
        "routed_query": search_query,
        "router": {
            "intent": router_intent or ("page_navigation" if page_navigation_intent else "qa"),
            "focus": router_focus,
            "must_terms": router_must_terms,
            "preferred_disciplines": router_preferred_disciplines,
            "preferred_page_types": router_preferred_page_types,
            "area_or_level": router_area_or_level,
            "strict": router_strict,
            "k": target_page_limit,
            "model": router_model,
        },
        "candidate_page_ids": [
            p.get("page_id")
            for p in selection_candidates
            if isinstance(p, dict) and p.get("page_id")
        ],
        "project_page_count": project_structure.get("total_pages", 0),
    }

    selection: dict[str, Any] = {}
    yield {"type": "tool_call", "tool": "select_pages_smart", "input": selection_input}
    trace.append({"type": "tool_call", "tool": "select_pages_smart", "input": selection_input})
    try:
        selection = await select_pages_smart(
            project_structure=project_structure,
            page_candidates=selection_candidates,
            query=query,
            history_context=history_context,
            viewing_context=viewing_context_str,
            memory_context=memory_context,
        )
        selection_result: dict[str, Any] = selection
    except Exception as e:
        logger.warning("Smart page selection failed in med mode, using deterministic fallback: %s", e)
        selection_result = {
            "error": str(e),
            "selected_pages": [],
            "chat_title": None,
            "conversation_title": None,
            "response": "",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }

    yield {"type": "tool_result", "tool": "select_pages_smart", "result": selection_result}
    trace.append({"type": "tool_result", "tool": "select_pages_smart", "result": selection_result})

    selected_page_ids: list[str] = []
    raw_selected_pages = selection.get("selected_pages")
    selector_relevance_by_id: dict[str, str] = {}
    if isinstance(raw_selected_pages, list):
        for item in raw_selected_pages:
            if not isinstance(item, dict):
                continue
            page_id = str(item.get("page_id") or "").strip()
            if page_id:
                selected_page_ids.append(page_id)
                relevance_text = str(item.get("relevance") or "").strip()
                if relevance_text and page_id not in selector_relevance_by_id:
                    selector_relevance_by_id[page_id] = relevance_text

    if not selected_page_ids:
        raw_page_ids = selection.get("page_ids")
        if isinstance(raw_page_ids, list):
            for item in raw_page_ids:
                page_id = str(item).strip()
                if page_id:
                    selected_page_ids.append(page_id)

    selected_page_ids = _dedupe_ids(selected_page_ids, limit=FAST_PAGE_LIMIT)

    vector_page_ids = _dedupe_ids([pid for pid in region_matches.keys() if pid], limit=FAST_PAGE_LIMIT)
    region_page_ids = list(vector_page_ids)
    keyword_page_ids = _dedupe_ids(
        [str(p.get("page_id")) for p in page_results if isinstance(p, dict) and p.get("page_id")],
        limit=FAST_PAGE_LIMIT,
    )
    strict_keyword_page_ids = [
        p.get("page_id")
        for p in strict_page_matches
        if isinstance(p, dict) and p.get("page_id")
    ]
    strict_keyword_page_ids = _dedupe_ids([str(pid) for pid in strict_keyword_page_ids], limit=FAST_PAGE_LIMIT)
    tree_page_ids: list[str] = []

    if router_strict and strict_keyword_page_ids:
        strict_id_set = set(strict_keyword_page_ids)
        selected_page_ids = [pid for pid in selected_page_ids if pid in strict_id_set]
        region_page_ids = [pid for pid in region_page_ids if pid in strict_id_set]

    if page_navigation_intent:
        tree_page_ids = _select_project_tree_page_ids(project_structure, query, max(target_page_limit, 6))

    page_lookup = _build_project_structure_page_lookup(project_structure)
    for page_result in page_results:
        if not isinstance(page_result, dict):
            continue
        page_id = str(page_result.get("page_id") or "").strip()
        if not page_id:
            continue
        entry = page_lookup.setdefault(page_id, {})
        sheet_card = page_result.get("sheet_card")
        if not isinstance(sheet_card, dict):
            sheet_card = _hydrate_sheet_card(page_result)
        entry.update(
            {
                "page_name": str(page_result.get("page_name") or entry.get("page_name") or "").strip(),
                "discipline": str(page_result.get("discipline") or entry.get("discipline") or "").strip(),
                "page_type": str(page_result.get("page_type") or entry.get("page_type") or "").strip(),
                "content": str(page_result.get("content") or entry.get("content") or "").strip(),
                "sheet_card": sheet_card,
            }
        )

    source_hit_sets = {
        "exact_title_hits": set(exact_title_page_ids),
        "reflection_keyword_hits": set(keyword_page_ids),
        "vector_hits": set(vector_page_ids),
        "region_hits": set(region_page_ids),
        "project_tree_hits": set(tree_page_ids),
        "strict_keyword_hits": set(strict_keyword_page_ids),
        "smart_selector_hits": set(selected_page_ids),
    }

    candidate_pool = _dedupe_ids(
        [
            *exact_title_page_ids,
            *strict_keyword_page_ids,
            *keyword_page_ids,
            *region_page_ids,
            *vector_page_ids,
            *selected_page_ids,
            *tree_page_ids,
        ]
    )
    if router_strict and strict_keyword_page_ids:
        strict_set = set(strict_keyword_page_ids)
        exact_set = set(exact_title_page_ids)
        candidate_pool = [pid for pid in candidate_pool if pid in strict_set or pid in exact_set]
        if not candidate_pool:
            candidate_pool = _dedupe_ids([*strict_keyword_page_ids, *exact_title_page_ids])

    if not candidate_pool:
        candidate_pool = _select_cover_index_fallback_page_ids(
            project_structure,
            max(target_page_limit, 6),
        )

    page_ids = _rank_candidate_page_ids_v2(
        candidate_pool,
        page_lookup=page_lookup,
        query=query,
        must_terms=router_must_terms,
        preferred_page_types=router_preferred_page_types,
        preferred_disciplines=router_preferred_disciplines,
        area_or_level=router_area_or_level,
        entity_terms=_extract_entity_terms(query),
        vector_hits=vector_page_ids,
        source_hit_sets=source_hit_sets,
        limit=max(target_page_limit, 6),
    )

    if not page_ids:
        page_ids = _select_cover_index_fallback_page_ids(project_structure, target_page_limit)

    if not page_ids:
        disciplines = project_structure.get("disciplines", [])
        if isinstance(disciplines, list):
            for discipline in disciplines:
                pages = discipline.get("pages", []) if isinstance(discipline, dict) else []
                if not isinstance(pages, list):
                    continue
                for page in pages:
                    if not isinstance(page, dict):
                        continue
                    page_id = page.get("page_id")
                    if page_id and page_id not in page_ids:
                        page_ids.append(page_id)
                    if len(page_ids) >= target_page_limit:
                        break
                if len(page_ids) >= target_page_limit:
                    break

    page_ids_before_cross_refs = list(dict.fromkeys(page_ids))
    cross_reference_page_ids: set[str] = set()
    if page_ids:
        page_ids = _expand_with_cross_reference_pages(db, project_id, page_ids)
        cross_reference_page_ids = set(page_ids) - set(page_ids_before_cross_refs)

    page_ids = list(dict.fromkeys([pid for pid in page_ids if pid]))[:target_page_limit]
    ordered_page_ids, page_map = _order_page_ids(db, page_ids, sort_by_sheet_number=True)

    for page_id, page_obj in page_map.items():
        entry = page_lookup.setdefault(page_id, {})
        page_name = getattr(page_obj, "page_name", None)
        if page_name:
            entry["page_name"] = page_name
        page_type = getattr(page_obj, "page_type", None)
        if page_type and not entry.get("page_type"):
            entry["page_type"] = page_type
        discipline_obj = getattr(page_obj, "discipline", None)
        discipline_name = getattr(discipline_obj, "display_name", None) if discipline_obj else None
        if discipline_name and not entry.get("discipline"):
            entry["discipline"] = discipline_name
        existing_sheet_card = entry.get("sheet_card")
        if not isinstance(existing_sheet_card, dict) or not existing_sheet_card:
            stored_sheet_card = getattr(page_obj, "sheet_card", None)
            if isinstance(stored_sheet_card, dict) and stored_sheet_card:
                entry["sheet_card"] = stored_sheet_card
            else:
                entry["sheet_card"] = build_sheet_card(
                    sheet_number=getattr(page_obj, "page_name", None),
                    page_type=getattr(page_obj, "page_type", None),
                    discipline_name=discipline_name,
                    sheet_reflection=getattr(page_obj, "sheet_reflection", None),
                    master_index=(
                        page_obj.master_index
                        if isinstance(getattr(page_obj, "master_index", None), dict)
                        else None
                    ),
                    keywords=None,
                    cross_references=getattr(page_obj, "cross_references", None),
                )

    candidate_sets = {
        "exact_title_hits": _build_candidate_set(exact_title_page_ids),
        "reflection_keyword_hits": _build_candidate_set(keyword_page_ids),
        "vector_hits": _build_candidate_set(vector_page_ids),
        "region_hits": _build_candidate_set(region_page_ids),
        "project_tree_hits": _build_candidate_set(tree_page_ids),
        "strict_keyword_hits": _build_candidate_set(strict_keyword_page_ids),
        "smart_selector_hits": _build_candidate_set(selected_page_ids),
    }
    source_hit_sets = {
        "exact_title_hits": set(candidate_sets["exact_title_hits"]["top_ids"]),
        "reflection_keyword_hits": set(candidate_sets["reflection_keyword_hits"]["top_ids"]),
        "vector_hits": set(candidate_sets["vector_hits"]["top_ids"]),
        "region_hits": set(candidate_sets["region_hits"]["top_ids"]),
        "project_tree_hits": set(candidate_sets["project_tree_hits"]["top_ids"]),
        "strict_keyword_hits": set(candidate_sets["strict_keyword_hits"]["top_ids"]),
        "smart_selector_hits": set(candidate_sets["smart_selector_hits"]["top_ids"]),
    }
    rank_breakdown = _build_rank_breakdown(
        query=query,
        ordered_page_ids=ordered_page_ids,
        page_lookup=page_lookup,
        must_terms=router_must_terms,
        preferred_page_types=router_preferred_page_types,
        preferred_disciplines=router_preferred_disciplines,
        area_or_level=router_area_or_level,
        entity_terms=_extract_entity_terms(query),
        vector_hits=vector_page_ids,
        source_hit_sets=source_hit_sets,
        top_n=target_page_limit,
    )
    final_selection = _build_final_selection_trace(
        ordered_page_ids=ordered_page_ids,
        page_lookup=page_lookup,
        target_page_limit=target_page_limit,
        page_navigation_intent=page_navigation_intent,
        source_hit_sets=source_hit_sets,
        selector_relevance_by_id=selector_relevance_by_id,
        cross_reference_page_ids=cross_reference_page_ids,
    )

    router_usage_raw = router_result.get("usage") if isinstance(router_result.get("usage"), dict) else {}
    selector_usage_raw = (
        selection_result.get("usage")
        if isinstance(selection_result.get("usage"), dict)
        else {}
    )
    router_input_tokens = _coerce_int(router_usage_raw.get("input_tokens") or router_usage_raw.get("inputTokens"))
    router_output_tokens = _coerce_int(router_usage_raw.get("output_tokens") or router_usage_raw.get("outputTokens"))
    selector_input_tokens = _coerce_int(selector_usage_raw.get("input_tokens") or selector_usage_raw.get("inputTokens"))
    selector_output_tokens = _coerce_int(
        selector_usage_raw.get("output_tokens") or selector_usage_raw.get("outputTokens")
    )
    token_cost = {
        "router": {
            "input_tokens": router_input_tokens,
            "output_tokens": router_output_tokens,
        },
        "selector": {
            "input_tokens": selector_input_tokens,
            "output_tokens": selector_output_tokens,
        },
        "total": {
            "input_tokens": router_input_tokens + selector_input_tokens,
            "output_tokens": router_output_tokens + selector_output_tokens,
        },
    }

    # 4) Select pages for frontend.
    selected_pages_payload: list[dict[str, Any]] = []
    if ordered_page_ids:
        yield {"type": "tool_call", "tool": "select_pages", "input": {"page_ids": ordered_page_ids}}
        trace.append({"type": "tool_call", "tool": "select_pages", "input": {"page_ids": ordered_page_ids}})
        try:
            result = await select_pages(db, page_ids=ordered_page_ids)
            if hasattr(result, "model_dump"):
                result = result.model_dump(by_alias=True, mode="json")
            if isinstance(result, dict):
                selected_pages_payload = result.get("pages") if isinstance(result.get("pages"), list) else []
            yield {"type": "tool_result", "tool": "select_pages", "result": result}
            trace.append({"type": "tool_result", "tool": "select_pages", "result": result})
        except Exception as e:
            logger.error("select_pages failed in med mode: %s", e)
            error_result = {"error": str(e)}
            yield {"type": "tool_result", "tool": "select_pages", "result": error_result}
            trace.append({"type": "tool_result", "tool": "select_pages", "result": error_result})

    # 5) Deterministic region selection.
    selected_regions, region_candidates_by_page = _select_med_region_candidates(
        ordered_page_ids=ordered_page_ids,
        page_map=page_map,
        region_matches=region_matches,
        query=query,
        must_terms=router_must_terms,
        preferred_page_types=router_preferred_page_types,
        entity_terms=_extract_entity_terms(query),
        total_limit=MED_TOTAL_HIGHLIGHT_LIMIT,
        per_page_limit=MED_HIGHLIGHTS_PER_PAGE,
    )

    # 6) Format Brain Mode regions directly for frontend (skip resolve_highlights).
    # Brain Mode regions already have normalized bboxes (0-1) and region IDs.
    # resolve_highlights() would convert to pixels and lose IDs.
    resolved_highlights: list[dict[str, Any]] = []
    for page_id in ordered_page_ids:
        page_regions = [r for r in selected_regions if r.get("page_id") == page_id]
        if not page_regions:
            continue

        words = []
        for region in page_regions:
            bbox = region.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            words.append({
                "id": region.get("region_id"),
                "text": region.get("label") or "",
                "bbox": {
                    "x0": bbox[0],
                    "y0": bbox[1],
                    "x1": bbox[2],
                    "y1": bbox[3],
                },
                "role": region.get("region_type"),
                "region_type": region.get("region_type"),
                "source": "brain_mode",
                "confidence": "medium",
            })

        if words:
            resolved_highlights.append({
                "page_id": page_id,
                "words": words,
            })

    # Emit trace events for debugging (same structure as before)
    resolve_input = {
        "highlight_count": len(selected_regions),
        "page_count": len(selected_pages_payload),
        "method": "brain_mode_direct",
    }
    yield {"type": "tool_call", "tool": "resolve_highlights", "input": resolve_input}
    trace.append({"type": "tool_call", "tool": "resolve_highlights", "input": resolve_input})

    resolve_result = {"highlights": resolved_highlights}
    yield {"type": "tool_result", "tool": "resolve_highlights", "result": resolve_result}
    trace.append({"type": "tool_result", "tool": "resolve_highlights", "result": resolve_result})

    query_plan = {
        "intent": router_intent or ("page_navigation" if page_navigation_intent else "qa"),
        "focus": router_focus or None,
        "must_terms": router_must_terms,
        "preferred_disciplines": router_preferred_disciplines,
        "preferred_page_types": router_preferred_page_types,
        "area_or_level": router_area_or_level,
        "strict": router_strict,
        "k": target_page_limit,
        "model": router_model,
        "ranker": "v2",
        "selector_rerank": True,
    }
    med_mode_trace_payload = {
        "query_plan": query_plan,
        "candidate_sets": candidate_sets,
        "rank_breakdown": rank_breakdown,
        "page_selection": final_selection,
        "region_candidates": region_candidates_by_page,
        "final_highlights": {
            "count": len(selected_regions),
            "resolved_page_count": len(resolved_highlights),
            "regions": [
                {
                    "page_id": region.get("page_id"),
                    "page_name": region.get("page_name"),
                    "region_id": region.get("region_id"),
                    "label": region.get("label"),
                    "region_type": region.get("region_type"),
                    "score": region.get("score"),
                    "reason": region.get("reason"),
                    "bbox": region.get("bbox"),
                }
                for region in selected_regions
            ],
        },
        "token_cost": token_cost,
    }
    yield {"type": "tool_result", "tool": "med_mode_trace", "result": med_mode_trace_payload}
    trace.append({"type": "tool_result", "tool": "med_mode_trace", "result": med_mode_trace_payload})

    response_text = selection.get("response") if isinstance(selection.get("response"), str) else ""
    response_text = response_text.strip()
    if not response_text:
        response_text = _build_med_mode_response_text(ordered_page_ids, page_map, selected_regions)
        if ordered_page_ids and not selected_regions:
            response_text = (
                "I pulled the best sheets, but available metadata was limited so highlights are broad."
            )

    if response_text:
        yield {"type": "text", "content": response_text}
        trace.append({"type": "reasoning", "content": response_text})

    input_tokens = token_cost["total"]["input_tokens"]
    output_tokens = token_cost["total"]["output_tokens"]
    tokens = _extract_query_tokens(query)
    fallback_title = " ".join(tokens[:3]).title() if tokens else "Query"
    display_title = str(selection.get("chat_title") or "").strip() or fallback_title
    conversation_title = str(selection.get("conversation_title") or "").strip() or display_title

    yield {
        "type": "done",
        "trace": trace,
        "usage": {"inputTokens": input_tokens, "outputTokens": output_tokens},
        "displayTitle": display_title,
        "conversationTitle": conversation_title,
        "highlights": [],
        "conceptName": None,
        "summary": None,
        "findings": [],
        "crossReferences": [],
        "gaps": [],
    }


async def run_agent_query_deep(
    db: Session,
    project_id: str,
    query: str,
    history_messages: list[dict[str, Any]] | None = None,
    viewing_context: dict[str, Any] | None = None,
) -> AsyncIterator[dict]:
    """
    Deep mode:
    - Same RAG page retrieval as fast mode
    - Streams Gemini thinking while exploring regions with vision
    - Returns structured findings/cross-references/gaps
    """
    from app.services.providers.gemini import explore_concept_with_vision_streaming
    from app.services.tools import (
        get_project_structure_summary,
        resolve_highlights,
        search_pages,
        select_pages,
    )
    from app.services.utils.search import search_pages_and_regions

    trace: list[dict] = []
    settings = get_settings()
    deep_v2_enabled = bool(getattr(settings, "deep_mode_vision_v2", False))
    deep_started_at = asyncio.get_running_loop().time()
    # Extract memory_context if passed through viewing_context (from Big Maestro)
    memory_context = ""
    if viewing_context and isinstance(viewing_context, dict):
        memory_context = viewing_context.get("memory_context", "")

    # 1) Project structure summary
    yield {"type": "tool_call", "tool": "list_project_pages", "input": {}}
    trace.append({"type": "tool_call", "tool": "list_project_pages", "input": {}})

    project_structure: dict[str, Any] = {"disciplines": [], "total_pages": 0}
    try:
        structure_result = await get_project_structure_summary(db, project_id=project_id)
        if isinstance(structure_result, dict):
            project_structure = structure_result
    except Exception as e:
        logger.warning("Project structure summary failed: %s", e)

    yield {"type": "tool_result", "tool": "list_project_pages", "result": project_structure}
    trace.append({"type": "tool_result", "tool": "list_project_pages", "result": project_structure})

    # 2) RAG region search
    yield {"type": "tool_call", "tool": "search_pages_and_regions", "input": {"query": query}}
    trace.append({"type": "tool_call", "tool": "search_pages_and_regions", "input": {"query": query}})

    try:
        region_matches = await search_pages_and_regions(db, query=query, project_id=project_id)
    except Exception as e:
        logger.exception("Region search failed: %s", e)
        yield {"type": "error", "message": f"Search failed: {str(e)}"}
        return

    yield {"type": "tool_result", "tool": "search_pages_and_regions", "result": region_matches}
    trace.append({"type": "tool_result", "tool": "search_pages_and_regions", "result": region_matches})

    page_ids = [pid for pid in region_matches.keys() if pid]

    # 3) Fallback keyword search when region retrieval is empty
    if not page_ids:
        yield {"type": "tool_call", "tool": "search_pages", "input": {"query": query}}
        trace.append({"type": "tool_call", "tool": "search_pages", "input": {"query": query}})
        page_results = await search_pages(db, query=query, project_id=project_id, limit=DEEP_PAGE_LIMIT)
        yield {"type": "tool_result", "tool": "search_pages", "result": page_results}
        trace.append({"type": "tool_result", "tool": "search_pages", "result": page_results})
        page_ids = [p.get("page_id") for p in page_results if p.get("page_id")]

    if not page_ids:
        disciplines = project_structure.get("disciplines", [])
        if isinstance(disciplines, list):
            for discipline in disciplines:
                pages = discipline.get("pages", []) if isinstance(discipline, dict) else []
                if not isinstance(pages, list):
                    continue
                for page in pages:
                    if not isinstance(page, dict):
                        continue
                    page_id = page.get("page_id")
                    if page_id and page_id not in page_ids:
                        page_ids.append(page_id)
                    if len(page_ids) >= DEEP_PAGE_LIMIT:
                        break
                if len(page_ids) >= DEEP_PAGE_LIMIT:
                    break

    if page_ids:
        page_ids = _expand_with_cross_reference_pages(db, project_id, page_ids)

    page_ids = list(dict.fromkeys([pid for pid in page_ids if pid]))[:DEEP_PAGE_LIMIT]
    ordered_page_ids, page_map = _order_page_ids(db, page_ids)

    selected_pages_payload: list[dict[str, Any]] = []
    # 4) Select pages so frontend and persistence stay consistent
    if ordered_page_ids:
        yield {"type": "tool_call", "tool": "select_pages", "input": {"page_ids": ordered_page_ids}}
        trace.append({"type": "tool_call", "tool": "select_pages", "input": {"page_ids": ordered_page_ids}})
        try:
            result = await select_pages(db, page_ids=ordered_page_ids)
            if hasattr(result, "model_dump"):
                result = result.model_dump(by_alias=True, mode="json")
            if isinstance(result, dict):
                selected_pages_payload = (
                    result.get("pages")
                    if isinstance(result.get("pages"), list)
                    else []
                )
            yield {"type": "tool_result", "tool": "select_pages", "result": result}
            trace.append({"type": "tool_result", "tool": "select_pages", "result": result})
        except Exception as e:
            logger.error("select_pages failed: %s", e)
            error_result = {"error": str(e)}
            yield {"type": "tool_result", "tool": "select_pages", "result": error_result}
            trace.append({"type": "tool_result", "tool": "select_pages", "result": error_result})

    if not ordered_page_ids:
        response_text = "I couldn't find a reliable set of sheets to analyze deeply."
        yield {"type": "text", "content": response_text}
        trace.append({"type": "reasoning", "content": response_text})
        tokens = _extract_query_tokens(query)
        display_title = " ".join(tokens[:3]).title() if tokens else "Query"
        yield {
            "type": "done",
            "trace": trace,
            "usage": {"inputTokens": 0, "outputTokens": 0},
            "displayTitle": display_title,
            "conversationTitle": display_title,
            "highlights": [],
            "conceptName": None,
            "summary": None,
            "findings": [],
            "crossReferences": [],
            "gaps": [],
        }
        return

    # 5) Prepare deep vision page payload
    query_tokens = _extract_query_tokens(query)
    history_context = _build_history_context(history_messages)
    viewing_context_str = _build_viewing_context_str(viewing_context)
    must_terms = query_tokens[:4]
    preferred_page_types: list[str] = []
    query_norm = _normalize_text(query)
    if "schedule" in query_norm:
        preferred_page_types.append("schedule")
    if "detail" in query_norm or "section" in query_norm or "elevation" in query_norm:
        preferred_page_types.append("detail_sheet")
    if "note" in query_norm or "legend" in query_norm:
        preferred_page_types.append("notes")

    verification_plan: dict[str, Any] = {}
    if deep_v2_enabled:
        verification_plan = _build_deep_verification_plan(
            query=query,
            ordered_page_ids=ordered_page_ids,
            page_map=page_map,
            region_matches=region_matches,
            must_terms=must_terms,
            preferred_page_types=preferred_page_types,
            max_pages=DEEP_PAGE_LIMIT,
            max_candidate_regions=DEEP_CANDIDATE_REGION_LIMIT,
            max_expansion_regions=DEEP_EXPANSION_REGION_LIMIT,
            max_micro_crops=DEEP_MICRO_CROP_LIMIT,
        )

    candidate_regions_by_page = (
        verification_plan.get("candidate_regions_by_page", {})
        if isinstance(verification_plan, dict)
        else {}
    )
    expansion_regions_by_page = (
        verification_plan.get("expansion_regions_by_page", {})
        if isinstance(verification_plan, dict)
        else {}
    )

    pages_for_vision: list[dict[str, Any]] = []
    for page_id in ordered_page_ids[:DEEP_PAGE_LIMIT]:
        page = page_map.get(page_id)
        if not page:
            continue

        image_bytes = await _load_page_image_bytes(page)
        if not image_bytes:
            continue

        raw_regions = page.regions if isinstance(page.regions, list) else []
        regions: list[dict[str, Any]] = []
        region_index_by_id: dict[str, int] = {}
        for idx, raw_region in enumerate(raw_regions):
            if not isinstance(raw_region, dict):
                continue
            region = dict(raw_region)
            region.pop("embedding", None)
            if not isinstance(region.get("bbox"), dict):
                continue
            region.setdefault("regionIndex", idx)
            if region.get("detailNumber") is None and region.get("detail_number") is not None:
                region["detailNumber"] = region.get("detail_number")
            region_id = region.get("id")
            if region_id:
                region_index_by_id[str(region_id)] = int(region["regionIndex"])
            regions.append(region)

        candidate_regions: list[dict[str, Any]] = []
        expansion_regions: list[dict[str, Any]] = []
        if deep_v2_enabled:
            candidate_regions = list(candidate_regions_by_page.get(str(page.id)) or [])
            expansion_regions = list(expansion_regions_by_page.get(str(page.id)) or [])
        else:
            for raw_region in (region_matches.get(str(page.id)) or [])[:DEEP_CANDIDATE_REGION_LIMIT]:
                if not isinstance(raw_region, dict):
                    continue
                region = dict(raw_region)
                region.pop("embedding", None)
                region_id = region.get("id")
                if region.get("regionIndex") is None and region_id and str(region_id) in region_index_by_id:
                    region["regionIndex"] = region_index_by_id[str(region_id)]
                if region.get("detailNumber") is None and region.get("detail_number") is not None:
                    region["detailNumber"] = region.get("detail_number")
                candidate_regions.append(region)

        context_markdown = (
            page.sheet_reflection
            or page.context_markdown
            or page.full_context
            or page.initial_context
            or ""
        )
        details = _filter_details(page.details if isinstance(page.details, list) else [], query_tokens)
        semantic_index = _filter_semantic_index(page.semantic_index, query_tokens)

        pages_for_vision.append(
            {
                "page_id": str(page.id),
                "page_name": page.page_name,
                "discipline": page.discipline.display_name if page.discipline else None,
                "context_markdown": context_markdown,
                "details": details,
                "semantic_index": semantic_index,
                "regions": regions,
                "candidate_regions": candidate_regions,
                "expansion_regions": expansion_regions,
                "master_index": page.master_index if isinstance(page.master_index, dict) else None,
                "image_bytes": image_bytes,
            }
        )

    if not pages_for_vision:
        response_text = "I found relevant sheets, but I couldn't load page images for deep analysis."
        yield {"type": "text", "content": response_text}
        trace.append({"type": "reasoning", "content": response_text})
        tokens = _extract_query_tokens(query)
        display_title = " ".join(tokens[:3]).title() if tokens else "Query"
        yield {
            "type": "done",
            "trace": trace,
            "usage": {"inputTokens": 0, "outputTokens": 0},
            "displayTitle": display_title,
            "conversationTitle": display_title,
            "highlights": [],
            "conceptName": None,
            "summary": None,
            "findings": [],
            "crossReferences": [],
            "gaps": [],
        }
        return

    verification_payload: Any = verification_plan if deep_v2_enabled else []

    vision_page_ids = [str(p.get("page_id")) for p in pages_for_vision if p.get("page_id")]
    tool_input = {"query": query, "page_ids": vision_page_ids}
    if deep_v2_enabled:
        tool_input["verification_mode"] = "v2"
    yield {"type": "tool_call", "tool": "explore_concept_with_vision", "input": tool_input}
    trace.append({"type": "tool_call", "tool": "explore_concept_with_vision", "input": tool_input})

    concept_result: dict[str, Any] = {}
    exploration_failed = False
    try:
        async for event in explore_concept_with_vision_streaming(
            query=query,
            pages=pages_for_vision,
            verification_plan=verification_payload,
            history_context=history_context,
            viewing_context=viewing_context_str,
        ):
            event_type = event.get("type")
            if event_type == "thinking":
                content = event.get("content")
                if isinstance(content, str) and content:
                    yield {"type": "thinking", "content": content}
                    trace.append({"type": "thinking", "content": content})
            elif event_type == "result":
                data = event.get("data")
                if isinstance(data, dict):
                    concept_result = data
    except Exception as e:
        if not deep_v2_enabled:
            logger.exception("Deep vision exploration failed: %s", e)
            yield {"type": "error", "message": f"Deep analysis failed: {str(e)}"}
            return
        logger.exception("Deep V2 vision exploration failed, using bounded fallback: %s", e)
        exploration_failed = True
        concept_result = {
            "concept_name": None,
            "summary": None,
            "findings": [],
            "cross_references": [],
            "gaps": ["Deep verification was inconclusive due to a vision execution failure."],
            "response": "I reviewed the top candidate sheets, but deep verification was inconclusive.",
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "fallback_used": True,
        }

    if deep_v2_enabled and not concept_result:
        exploration_failed = True
        concept_result = {
            "concept_name": None,
            "summary": None,
            "findings": [],
            "cross_references": [],
            "gaps": ["Deep verification returned no structured findings."],
            "response": "I reviewed the top candidate sheets, but I could not verify a reliable result.",
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "fallback_used": True,
        }

    raw_findings = (
        concept_result.get("findings")
        if isinstance(concept_result.get("findings"), list)
        else []
    )
    normalized_findings, downgraded_verified_count = _normalize_deep_findings_for_contract(
        raw_findings,
        enforce_verified_evidence=deep_v2_enabled,
    )
    truncated_finding_count = max(0, len(normalized_findings) - DEEP_MAX_FINDINGS)
    if len(normalized_findings) > DEEP_MAX_FINDINGS:
        normalized_findings = normalized_findings[:DEEP_MAX_FINDINGS]
    concept_result["findings"] = normalized_findings
    if downgraded_verified_count > 0:
        gaps = concept_result.get("gaps")
        if not isinstance(gaps, list):
            gaps = []
        gaps.append(
            f"Downgraded {downgraded_verified_count} verified claim(s) due to missing evidence artifacts."
        )
        concept_result["gaps"] = gaps
    if truncated_finding_count > 0:
        gaps = concept_result.get("gaps")
        if not isinstance(gaps, list):
            gaps = []
        gaps.append(
            f"Trimmed {truncated_finding_count} finding(s) to enforce bounded Deep output size."
        )
        concept_result["gaps"] = gaps

    yield {
        "type": "tool_result",
        "tool": "explore_concept_with_vision",
        "result": concept_result,
    }
    trace.append(
        {
            "type": "tool_result",
            "tool": "explore_concept_with_vision",
            "result": concept_result,
        }
    )

    # 6) Resolve Deep findings into highlight overlays.
    highlight_specs = _build_deep_highlight_specs_from_findings(normalized_findings)
    resolve_input = {
        "highlight_count": len(highlight_specs),
        "page_count": len(selected_pages_payload),
    }
    yield {"type": "tool_call", "tool": "resolve_highlights", "input": resolve_input}
    trace.append({"type": "tool_call", "tool": "resolve_highlights", "input": resolve_input})

    resolved_highlights: list[dict[str, Any]] = []
    try:
        if selected_pages_payload and highlight_specs:
            resolved_highlights = resolve_highlights(
                selected_pages_payload,
                highlight_specs,
                query_tokens=query_tokens,
            )
    except Exception as e:
        logger.warning("resolve_highlights failed in deep mode: %s", e)
        resolved_highlights = []

    resolve_result = {"highlights": resolved_highlights}
    yield {"type": "tool_result", "tool": "resolve_highlights", "result": resolve_result}
    trace.append({"type": "tool_result", "tool": "resolve_highlights", "result": resolve_result})

    usage_raw = concept_result.get("usage") if isinstance(concept_result.get("usage"), dict) else {}

    def _to_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    input_tokens = _to_int(usage_raw.get("input_tokens") or usage_raw.get("inputTokens"))
    output_tokens = _to_int(usage_raw.get("output_tokens") or usage_raw.get("outputTokens"))
    token_cost = {
        "vision": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
        "total": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
    }

    page_selection_summary = [
        {
            "page_id": str(page.get("page_id") or ""),
            "page_name": str(page.get("page_name") or "") or None,
            "candidate_region_count": len(page.get("candidate_regions") or []),
            "expansion_region_count": len(page.get("expansion_regions") or []),
        }
        for page in pages_for_vision
    ]
    finding_summary = _summarize_deep_findings(normalized_findings)
    pass_counts = _extract_deep_pass_counts(
        normalized_findings,
        concept_result.get("execution_summary"),
    )
    execution_summary = {
        "deep_v2_enabled": deep_v2_enabled,
        "fallback_used": bool(concept_result.get("fallback_used")) or exploration_failed,
        "inspected_page_count": len(pages_for_vision),
        "candidate_region_count": sum(len(page.get("candidate_regions") or []) for page in pages_for_vision),
        "expanded_region_count": sum(len(page.get("expansion_regions") or []) for page in pages_for_vision),
        "resolved_highlight_pages": len(resolved_highlights),
        "downgraded_verified_claims": downgraded_verified_count,
        "latency_ms": int(max(0.0, (asyncio.get_running_loop().time() - deep_started_at) * 1000)),
        "pass_1": pass_counts["pass_1"],
        "pass_2": pass_counts["pass_2"],
        "pass_3": pass_counts["pass_3"],
        "pass_total": pass_counts["pass_total"],
    }
    if isinstance(verification_plan, dict) and isinstance(verification_plan.get("budgets"), dict):
        execution_summary["budget"] = verification_plan.get("budgets")

    query_plan_payload = (
        verification_plan.get("query_plan")
        if isinstance(verification_plan, dict) and isinstance(verification_plan.get("query_plan"), dict)
        else {
            "intent": "verification",
            "query_tokens": query_tokens[:8],
            "must_terms": must_terms[:4],
            "preferred_page_types": preferred_page_types[:3],
            "evidence_targets": _infer_deep_evidence_targets(query, query_tokens),
        }
    )
    verification_trace_payload = (
        verification_plan
        if deep_v2_enabled and isinstance(verification_plan, dict)
        else {
            "budgets": {
                "max_pages": DEEP_PAGE_LIMIT,
                "max_candidate_regions": DEEP_CANDIDATE_REGION_LIMIT,
                "max_expansion_regions": DEEP_EXPANSION_REGION_LIMIT,
                "max_micro_crops": DEEP_MICRO_CROP_LIMIT,
            },
            "steps": [],
        }
    )

    deep_mode_trace_payload = {
        "query_plan": query_plan_payload,
        "page_selection": page_selection_summary,
        "verification_plan": verification_trace_payload,
        "execution_summary": execution_summary,
        "final_findings": finding_summary,
        "token_cost": token_cost,
    }
    yield {"type": "tool_result", "tool": "deep_mode_trace", "result": deep_mode_trace_payload}
    trace.append({"type": "tool_result", "tool": "deep_mode_trace", "result": deep_mode_trace_payload})

    response_text = concept_result.get("response")
    if not isinstance(response_text, str) or not response_text.strip():
        summary = concept_result.get("summary")
        if isinstance(summary, str) and summary.strip():
            response_text = summary.strip()
        else:
            top_names = [
                page_map[pid].page_name
                for pid in ordered_page_ids[:3]
                if pid in page_map and page_map[pid].page_name
            ]
            if top_names:
                response_text = f"I ran a deep review on {', '.join(top_names)}."
            else:
                response_text = "Deep analysis complete."

    yield {"type": "text", "content": response_text}
    trace.append({"type": "reasoning", "content": response_text})

    concept_name = concept_result.get("concept_name")
    if not isinstance(concept_name, str):
        concept_name = None
    summary = concept_result.get("summary")
    if not isinstance(summary, str):
        summary = None
    findings = normalized_findings
    cross_references = concept_result.get("cross_references")
    if not isinstance(cross_references, list):
        cross_references = concept_result.get("crossReferences") if isinstance(concept_result.get("crossReferences"), list) else []
    gaps = concept_result.get("gaps") if isinstance(concept_result.get("gaps"), list) else []

    tokens = _extract_query_tokens(query)
    display_title = concept_name or (" ".join(tokens[:3]).title() if tokens else "Query")

    yield {
        "type": "done",
        "trace": trace,
        "usage": {"inputTokens": input_tokens, "outputTokens": output_tokens},
        "displayTitle": display_title,
        "conversationTitle": display_title,
        "highlights": [],
        "conceptName": concept_name,
        "summary": summary,
        "findings": findings,
        "crossReferences": cross_references,
        "gaps": gaps,
    }


async def run_agent_query_gemini(
    db: Session,
    project_id: str,
    query: str,
    history_messages: list[dict[str, Any]] | None = None,
    viewing_context: dict[str, Any] | None = None,
) -> AsyncIterator[dict]:
    """
    Backwards-compatible alias for the default fast-mode Gemini path.
    """
    async for event in run_agent_query_fast(db, project_id, query, history_messages, viewing_context):
        yield event


async def run_agent_query_grok(
    db: Session,
    project_id: str,
    query: str,
    history_messages: list[dict[str, Any]] | None = None,
    viewing_context: dict[str, Any] | None = None,
) -> AsyncIterator[dict]:
    """
    Legacy agent query using Grok 4.1 Fast via OpenRouter with multi-turn tool calling.

    Set AGENT_BACKEND=grok to use this implementation.
    """
    from app.services.tools import search_pages, search_pointers, get_project_structure_summary

    settings = get_settings()
    if not settings.openrouter_api_key:
        yield {"type": "error", "message": "OpenRouter API key not configured"}
        return

    # Use OpenAI client with OpenRouter base URL
    client = openai.AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
    )

    # PRE-FETCH: Run searches + project structure before LLM call to eliminate roundtrips
    # This runs in parallel using asyncio
    # NOTE: Using get_project_structure_summary (lightweight) instead of list_project_pages
    # to avoid loading all pointers into memory

    # Yield pre-fetch status
    yield {"type": "tool_call", "tool": "list_project_pages", "input": {}}
    yield {"type": "tool_call", "tool": "search_pages", "input": {"query": query}}
    yield {"type": "tool_call", "tool": "search_pointers", "input": {"query": query}}

    # Run all three in parallel - using lightweight summary for project structure
    project_structure_dict, page_results, pointer_results = await asyncio.gather(
        get_project_structure_summary(db, project_id=project_id),
        search_pages(db, query=query, project_id=project_id, limit=10),
        search_pointers(db, query=query, project_id=project_id, limit=10),
    )

    # project_structure_dict is already a dict (not Pydantic), no conversion needed

    # Yield pre-fetch results
    yield {"type": "tool_result", "tool": "list_project_pages", "result": project_structure_dict}
    yield {"type": "tool_result", "tool": "search_pages", "result": page_results}
    yield {"type": "tool_result", "tool": "search_pointers", "result": pointer_results}

    # Build pre-fetch context to inject into prompt
    prefetch_context = f"""

PRE-FETCHED DATA (already executed - do NOT call these tools again):

PROJECT STRUCTURE (all disciplines and pages):
{json.dumps(project_structure_dict, indent=2)}

SEARCH RESULTS for "{query}":

Pages matching query:
{json.dumps(page_results, indent=2)}

Pointers matching query:
{json.dumps(pointer_results, indent=2)}

Use these results directly. Call select_pages/select_pointers with the relevant IDs from above.
If the search results are empty but you can identify relevant pages from the PROJECT STRUCTURE, use those page_ids."""

    system_content = AGENT_SYSTEM_PROMPT + prefetch_context

    # Add viewing context if user is currently viewing a specific page
    if viewing_context:
        page_name = viewing_context.get("page_name", "unknown page")
        discipline = viewing_context.get("discipline_name")
        if discipline:
            system_content += f"""

CURRENT VIEW: The user is currently viewing page {page_name} from {discipline}. This may or may not be relevant to their question - only reference it if it naturally relates to what they're asking."""
        else:
            system_content += f"""

CURRENT VIEW: The user is currently viewing page {page_name}. This may or may not be relevant to their question - only reference it if it naturally relates to what they're asking."""

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_content},
    ]

    # Add history messages if this is a multi-turn conversation
    if history_messages:
        messages.extend(history_messages)
        logger.info(f"Added {len(history_messages)} history messages to conversation")

    # Add current user query
    messages.append({"role": "user", "content": query})

    # Initialize trace with pre-fetch calls
    trace: list[dict] = [
        {"type": "tool_call", "tool": "list_project_pages", "input": {}},
        {"type": "tool_result", "tool": "list_project_pages", "result": project_structure_dict},
        {"type": "tool_call", "tool": "search_pages", "input": {"query": query}},
        {"type": "tool_result", "tool": "search_pages", "result": page_results},
        {"type": "tool_call", "tool": "search_pointers", "input": {"query": query}},
        {"type": "tool_result", "tool": "search_pointers", "result": pointer_results},
    ]
    total_input_tokens = 0
    total_output_tokens = 0
    display_title: str | None = None
    conversation_title: str | None = None

    try:
        while True:
            # 60 second timeout for API connection + first response
            try:
                stream = await asyncio.wait_for(
                    client.chat.completions.create(
                        model="x-ai/grok-4.1-fast",
                        max_tokens=4096,
                        tools=TOOL_DEFINITIONS,
                        messages=messages,
                        stream=True,
                        temperature=0,  # More consistent results
                    ),
                    timeout=60.0,
                )
            except asyncio.TimeoutError:
                logger.error("OpenRouter API timeout after 60 seconds")
                yield {"type": "error", "message": "Request timed out. Please try again."}
                return

            # Collect streaming response
            current_text = ""
            tool_calls_data: dict[int, dict] = {}  # index -> {id, name, arguments}

            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                if not choice:
                    continue

                delta = choice.delta

                # Stream text content
                if delta.content:
                    yield {"type": "text", "content": delta.content}
                    current_text += delta.content

                # Accumulate tool calls (they come in chunks)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_data:
                            tool_calls_data[idx] = {
                                "id": tc.id or "",
                                "name": tc.function.name if tc.function and tc.function.name else "",
                                "arguments": "",
                            }
                        if tc.id:
                            tool_calls_data[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_data[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_data[idx]["arguments"] += tc.function.arguments

                # Track usage from final chunk
                if chunk.usage:
                    total_input_tokens += chunk.usage.prompt_tokens or 0
                    total_output_tokens += chunk.usage.completion_tokens or 0

            # Add accumulated text to trace
            if current_text:
                trace.append({"type": "reasoning", "content": current_text})

            # If no tool calls, we're done
            if not tool_calls_data:
                break

            # Process tool calls
            tool_calls_list = []
            for idx in sorted(tool_calls_data.keys()):
                tc_data = tool_calls_data[idx]
                tool_name = tc_data["name"]
                try:
                    tool_input = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                except json.JSONDecodeError:
                    tool_input = {}

                tool_calls_list.append({
                    "id": tc_data["id"],
                    "name": tool_name,
                    "input": tool_input,
                })

                yield {"type": "tool_call", "tool": tool_name, "input": tool_input}
                trace.append({"type": "tool_call", "tool": tool_name, "input": tool_input})

            # Execute tools and build results
            tool_results = []
            assistant_tool_calls = []

            for tc in tool_calls_list:
                tool_name = tc["name"]
                tool_input = tc["input"]
                tool_id = tc["id"]

                # Handle set_display_title specially - no DB access needed
                if tool_name == "set_display_title":
                    chat_title = tool_input.get("chat_title", "")
                    conv_title = tool_input.get("conversation_title", "")
                    # Clean up titles - strip leading colons, quotes, and whitespace
                    if chat_title:
                        chat_title = chat_title.strip().lstrip(':').strip().strip('"').strip("'").strip()
                    if conv_title:
                        conv_title = conv_title.strip().lstrip(':').strip().strip('"').strip("'").strip()
                    display_title = chat_title[:100] if chat_title else None
                    conversation_title = conv_title[:200] if conv_title else display_title
                    result = {"success": True, "chat_title": display_title, "conversation_title": conversation_title}
                    logger.info(f"Titles set - chat: {display_title}, conversation: {conversation_title}")
                else:
                    result = await execute_tool(db, project_id, tool_name, tool_input)

                result_json = json.dumps(result)

                yield {"type": "tool_result", "tool": tool_name, "result": result}
                trace.append({"type": "tool_result", "tool": tool_name, "result": result})

                # Build assistant tool_calls for message history
                assistant_tool_calls.append({
                    "id": tool_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(tool_input),
                    },
                })

                # Build tool result message
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": result_json,
                })

            # Add assistant message with tool calls
            assistant_message: dict[str, Any] = {"role": "assistant"}
            if current_text:
                assistant_message["content"] = current_text
            if assistant_tool_calls:
                assistant_message["tool_calls"] = assistant_tool_calls
            messages.append(assistant_message)

            # Add tool results
            messages.extend(tool_results)

        # Final response with trace, usage, and titles
        yield {
            "type": "done",
            "trace": trace,
            "usage": {
                "inputTokens": total_input_tokens,
                "outputTokens": total_output_tokens,
            },
            "displayTitle": display_title,
            "conversationTitle": conversation_title,
        }

    except openai.APIError as e:
        logger.exception(f"OpenRouter API error: {e}")
        yield {"type": "error", "message": f"API error: {str(e)}"}
    except Exception as e:
        logger.exception(f"Agent error: {e}")
        yield {"type": "error", "message": str(e)}
