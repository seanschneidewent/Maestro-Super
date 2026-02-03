"""Utilities for building compact reflection-first sheet cards."""

from __future__ import annotations

import re
from typing import Any

_STOP_WORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "must",
    "can",
    "it",
    "its",
    "this",
    "that",
    "these",
    "those",
    "what",
    "which",
    "who",
    "whom",
    "where",
    "when",
    "why",
    "how",
    "all",
    "each",
    "every",
    "both",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "just",
    "also",
}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _dedupe(values: list[str], limit: int) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _normalize_text(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
        if len(deduped) >= limit:
            break
    return deduped


def _compact_line(value: str) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    text = re.sub(r"^#{1,6}\s*", "", text)
    text = re.sub(r"^[\-\*\u2022]\s*", "", text)
    text = re.sub(r"^\d+[\.\)]\s*", "", text)
    return _normalize_text(text.strip(":"))


def _extract_title(lines: list[str], fallback: str) -> str:
    for line in lines:
        heading = _compact_line(line)
        if not heading:
            continue
        return heading[:180]
    return _normalize_text(fallback)[:180]


def _extract_summary(reflection: str, title: str) -> str:
    if not reflection:
        return ""

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", reflection) if p.strip()]
    normalized_title = _normalize_text(title).casefold()

    for paragraph in paragraphs:
        compact = _compact_line(paragraph)
        if not compact:
            continue
        if normalized_title and compact.casefold() == normalized_title:
            continue
        if re.match(r"^#{1,6}\s+", paragraph.strip()):
            continue
        return compact[:320]
    return ""


def _extract_headings(reflection: str) -> list[str]:
    headings: list[str] = []
    for raw_line in reflection.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^#{1,6}\s+", line):
            headings.append(_compact_line(line))
            continue
        # Brain mode often emits markdown bold labels for section headers.
        bold_header = re.match(r"^\*\*([^*]{2,120})\*\*:?\s*$", line)
        if bold_header:
            headings.append(_compact_line(bold_header.group(1)))
    return _dedupe(headings, limit=12)


def _extract_cross_reference_sheets(cross_references: Any) -> list[str]:
    if not isinstance(cross_references, list):
        return []
    sheets: list[str] = []
    for ref in cross_references:
        if isinstance(ref, str):
            sheet = _normalize_text(ref)
        elif isinstance(ref, dict):
            sheet = _normalize_text(str(ref.get("sheet") or ref.get("page") or ""))
        else:
            sheet = ""
        if sheet:
            sheets.append(sheet)
    return _dedupe(sheets, limit=16)


def _extract_keywords(
    *,
    title: str,
    summary: str,
    headings: list[str],
    master_index: dict[str, Any] | None,
    existing_keywords: list[str] | None,
) -> list[str]:
    keywords: list[str] = []

    if isinstance(existing_keywords, list):
        keywords.extend(str(v) for v in existing_keywords if v is not None)

    if isinstance(master_index, dict):
        for value in master_index.get("keywords", []):
            if value is None:
                continue
            keywords.append(str(value))

        for value in master_index.get("items", []):
            if isinstance(value, dict):
                item_text = value.get("name") or value.get("label") or value.get("title")
                if item_text:
                    keywords.append(str(item_text))
            elif value is not None:
                keywords.append(str(value))

    keywords.extend(headings)
    keywords.extend([title, summary])

    lexical_tokens: list[str] = []
    for text in keywords:
        for token in re.findall(r"[a-z0-9][a-z0-9\-]{1,24}", text.lower()):
            if token in _STOP_WORDS:
                continue
            if len(token) <= 2:
                continue
            lexical_tokens.append(token)

    return _dedupe([*keywords, *lexical_tokens], limit=40)


def _extract_entities(*texts: str) -> list[str]:
    entities: list[str] = []
    joined = "\n".join(texts)
    if not joined.strip():
        return []

    for pattern in (
        r"\b[A-Z]{1,6}-\d+[A-Z0-9\-]*\b",
        r"\b[A-Z]{2,8}\d+[A-Z0-9\-]*\b",
        r"\b(?:RTU|AHU|FCU|EF|VAV|WIC|MCC|ATS|PANEL)\s*[-:]?\s*[A-Z0-9\-]+\b",
        r"\b(?:LEVEL|FLOOR)\s+\d+\b",
    ):
        entities.extend(re.findall(pattern, joined, flags=re.IGNORECASE))

    cleaned = [_normalize_text(entity).upper() for entity in entities]
    return _dedupe(cleaned, limit=20)


def build_sheet_card(
    *,
    sheet_number: str | None,
    page_type: str | None,
    discipline_name: str | None,
    sheet_reflection: str | None,
    master_index: dict[str, Any] | None = None,
    keywords: list[str] | None = None,
    cross_references: Any = None,
) -> dict[str, Any]:
    """Build a compact metadata card used for fast-mode routing and ranking."""
    reflection = str(sheet_reflection or "").strip()
    reflection_lines = [line.strip() for line in reflection.splitlines() if line.strip()]

    title = _extract_title(reflection_lines, fallback=str(sheet_number or ""))
    summary = _extract_summary(reflection, title=title)
    headings = _extract_headings(reflection)
    cross_reference_sheets = _extract_cross_reference_sheets(cross_references)
    reflection_keywords = _extract_keywords(
        title=title,
        summary=summary,
        headings=headings,
        master_index=master_index if isinstance(master_index, dict) else None,
        existing_keywords=keywords if isinstance(keywords, list) else None,
    )
    entities = _extract_entities(
        title,
        summary,
        reflection,
        " ".join(reflection_keywords),
    )

    return {
        "reflection_title": title or None,
        "reflection_summary": summary or None,
        "reflection_headings": headings,
        "reflection_keywords": reflection_keywords,
        "reflection_entities": entities,
        "sheet_number": _normalize_text(str(sheet_number or "")) or None,
        "page_type": _normalize_text(str(page_type or "")) or None,
        "discipline_name": _normalize_text(str(discipline_name or "")) or None,
        "cross_references": cross_reference_sheets,
    }

