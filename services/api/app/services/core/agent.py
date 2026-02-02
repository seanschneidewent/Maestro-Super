"""Query agent for navigating construction plan graph.

Uses Gemini structured output for single-shot queries (fast path)
with Grok 4.1 Fast via OpenRouter as fallback.
"""

import asyncio
import json
import logging
import os
import re
from typing import Any, AsyncIterator

import openai
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.models.discipline import Discipline
from app.models.page import Page

logger = logging.getLogger(__name__)

VISION_PAGE_LIMIT = 3
REGIONS_PER_PAGE_LIMIT = 3
REGION_QUERY_LIMIT = 6


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
) -> AsyncIterator[dict]:
    """
    Execute agent query with streaming events.

    Uses AGENT_BACKEND env var to select implementation:
    - "gemini" (default): Fast single-shot Gemini structured output
    - "grok": Multi-turn Grok 4.1 Fast via OpenRouter (legacy)

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
    """
    backend = os.environ.get("AGENT_BACKEND", "gemini").lower()

    if backend == "grok":
        async for event in run_agent_query_grok(db, project_id, query, history_messages, viewing_context):
            yield event
    else:
        async for event in run_agent_query_gemini(db, project_id, query, history_messages, viewing_context):
            yield event


async def run_agent_query_gemini(
    db: Session,
    project_id: str,
    query: str,
    history_messages: list[dict[str, Any]] | None = None,
    viewing_context: dict[str, Any] | None = None,
) -> AsyncIterator[dict]:
    """
    Query-time vision flow:
    - Vector search pages + regions
    - Crop to relevant regions
    - Answer with precise highlights
    """
    from app.services.core.query_vision import crop_region, query_with_vision
    from app.services.tools import search_pages, select_pages
    from app.services.utils.search import search_pages_and_regions

    trace: list[dict] = []

    # 1) Vector search for relevant regions
    yield {"type": "tool_call", "tool": "search_pages_and_regions", "input": {"query": query}}
    trace.append({"type": "tool_call", "tool": "search_pages_and_regions", "input": {"query": query}})

    try:
        region_matches = await search_pages_and_regions(db, query=query, project_id=project_id)
    except Exception as e:
        logger.exception(f"Region search failed: {e}")
        yield {"type": "error", "message": f"Search failed: {str(e)}"}
        return

    yield {"type": "tool_result", "tool": "search_pages_and_regions", "result": region_matches}
    trace.append({"type": "tool_result", "tool": "search_pages_and_regions", "result": region_matches})

    page_ids = list(region_matches.keys())

    # 2) Fallback to keyword search if no region matches
    page_results = []
    if not page_ids:
        yield {"type": "tool_call", "tool": "search_pages", "input": {"query": query}}
        trace.append({"type": "tool_call", "tool": "search_pages", "input": {"query": query}})
        page_results = await search_pages(db, query=query, project_id=project_id, limit=5)
        yield {"type": "tool_result", "tool": "search_pages", "result": page_results}
        trace.append({"type": "tool_result", "tool": "search_pages", "result": page_results})
        page_ids = [p.get("page_id") for p in page_results if p.get("page_id")]

    # Expand with cross-referenced sheets from top matches (lower priority).
    if page_ids:
        pages_for_cross_refs = _load_pages_for_vision(db, page_ids[:3])
        cross_ref_sheet_names: set[str] = set()
        for page in pages_for_cross_refs:
            cross_ref_sheet_names.update(_extract_cross_reference_sheet_names(page.cross_references))

        if cross_ref_sheet_names:
            cross_ref_pages = (
                db.query(Page)
                .join(Discipline)
                .filter(
                    Discipline.project_id == project_id,
                    Page.page_name.in_(list(cross_ref_sheet_names)),
                )
                .order_by(Page.page_name)
                .limit(3)
                .all()
            )
            cross_ref_ids = [str(p.id) for p in cross_ref_pages]
            page_ids = page_ids + [pid for pid in cross_ref_ids if pid not in page_ids]

    # De-dupe page IDs while preserving order
    page_ids = list(dict.fromkeys([pid for pid in page_ids if pid]))

    # Order pages by sheet number where possible
    pages_for_order = _load_pages_for_vision(db, page_ids)
    page_map = {str(p.id): p for p in pages_for_order}
    ordered_page_ids = sorted(
        page_ids,
        key=lambda pid: _page_sort_key(page_map.get(pid).page_name if page_map.get(pid) else ""),
    )

    # 3) Select pages for frontend display
    pages_result = None
    if ordered_page_ids:
        yield {"type": "tool_call", "tool": "select_pages", "input": {"page_ids": ordered_page_ids}}
        trace.append({"type": "tool_call", "tool": "select_pages", "input": {"page_ids": ordered_page_ids}})
        try:
            result = await select_pages(db, page_ids=ordered_page_ids)
            if hasattr(result, "model_dump"):
                result = result.model_dump(by_alias=True, mode="json")
            pages_result = result
            yield {"type": "tool_result", "tool": "select_pages", "result": result}
            trace.append({"type": "tool_result", "tool": "select_pages", "result": result})
        except Exception as e:
            logger.error(f"select_pages failed: {e}")
            error_result = {"error": str(e)}
            yield {"type": "tool_result", "tool": "select_pages", "result": error_result}
            trace.append({"type": "tool_result", "tool": "select_pages", "result": error_result})

    # 4) Query-time vision on matching regions
    answer_candidates: list[dict] = []
    highlight_map: dict[str, list[dict]] = {}

    vision_page_ids = ordered_page_ids[:VISION_PAGE_LIMIT]
    vision_pages = [page_map[pid] for pid in vision_page_ids if pid in page_map]

    if vision_pages:
        from app.services.utils.storage import download_file
        from app.services.providers.pdf_renderer import pdf_page_to_image

        query_count = 0

        for page in vision_pages:
            if query_count >= REGION_QUERY_LIMIT:
                break

            image_bytes = None
            try:
                if page.page_image_path and str(page.page_image_path).lower().endswith(".png"):
                    image_bytes = await download_file(page.page_image_path)
                elif page.file_path and str(page.file_path).lower().endswith(".pdf"):
                    pdf_bytes = await download_file(page.file_path)
                    image_bytes = pdf_page_to_image(pdf_bytes, page.page_index, dpi=150)
                elif page.file_path and str(page.file_path).lower().endswith(".png"):
                    image_bytes = await download_file(page.file_path)
            except Exception as e:
                logger.warning(f"Failed to load image for page {page.page_name}: {e}")
                image_bytes = None

            if not image_bytes:
                continue

            regions = region_matches.get(str(page.id)) or []
            if regions:
                regions = sorted(regions, key=lambda r: r.get("_similarity", 0.0), reverse=True)
            regions = regions[:REGIONS_PER_PAGE_LIMIT]

            for region in regions:
                if query_count >= REGION_QUERY_LIMIT:
                    break

                try:
                    bbox = region.get("bbox")
                    if not isinstance(bbox, dict):
                        continue
                    cropped_bytes, crop_box = crop_region(image_bytes, bbox)
                    vision_result = await query_with_vision(
                        question=query,
                        page_image_bytes=cropped_bytes,
                        relevant_regions=[region],
                        page_context=page.sheet_reflection or "",
                        page_name=page.page_name,
                    )
                except Exception as e:
                    logger.warning(f"Query vision failed for {page.page_name}: {e}")
                    continue

                query_count += 1

                answer = vision_result.get("answer") or ""
                confidence = vision_result.get("confidence") or "low"
                if answer:
                    answer_candidates.append({
                        "page_name": page.page_name,
                        "region_label": region.get("label") or region.get("type") or "",
                        "answer": answer,
                        "confidence": confidence,
                    })

                elements = vision_result.get("elements") or []
                if elements:
                    words = highlight_map.setdefault(str(page.id), [])
                    for element in elements:
                        if not isinstance(element, dict):
                            continue
                        bbox = element.get("bbox") or {}
                        x0 = bbox.get("x0")
                        y0 = bbox.get("y0")
                        x1 = bbox.get("x1")
                        y1 = bbox.get("y1")
                        try:
                            x0 = int(round(float(x0)))
                            y0 = int(round(float(y0)))
                            x1 = int(round(float(x1)))
                            y1 = int(round(float(y1)))
                        except Exception:
                            continue

                        x0 = crop_box["x0"] + x0
                        y0 = crop_box["y0"] + y0
                        x1 = crop_box["x0"] + x1
                        y1 = crop_box["y0"] + y1

                        if x1 < x0:
                            x0, x1 = x1, x0
                        if y1 < y0:
                            y0, y1 = y1, y0

                        words.append({
                            "id": None,
                            "text": element.get("text") or "",
                            "bbox": {
                                "x0": x0,
                                "y0": y0,
                                "x1": x1,
                                "y1": y1,
                                "width": max(0, x1 - x0),
                                "height": max(0, y1 - y0),
                            },
                            "role": element.get("role"),
                            "source": "agent",
                        })

    # 5) Emit resolve_highlights tool result for frontend
    resolved_highlights = [
        {"page_id": page_id, "words": words}
        for page_id, words in highlight_map.items()
        if words
    ]

    if resolved_highlights:
        yield {"type": "tool_call", "tool": "resolve_highlights", "input": {"page_ids": list(highlight_map.keys())}}
        yield {"type": "tool_result", "tool": "resolve_highlights", "result": {"highlights": resolved_highlights}}
        trace.append({"type": "tool_call", "tool": "resolve_highlights", "input": {"page_ids": list(highlight_map.keys())}})
        trace.append({"type": "tool_result", "tool": "resolve_highlights", "result": {"highlights": resolved_highlights}})

    # 6) Compose response text
    response_text = ""
    if answer_candidates:
        confidence_rank = {"high": 3, "medium": 2, "low": 1}
        answer_candidates.sort(
            key=lambda a: confidence_rank.get(a.get("confidence"), 0),
            reverse=True,
        )
        primary = answer_candidates[0]
        prefix = f"{primary['page_name']} {primary['region_label']}".strip()
        response_text = f"{prefix}: {primary['answer']}".strip()
        if len(answer_candidates) > 1:
            secondary = answer_candidates[1]
            secondary_prefix = f"{secondary['page_name']} {secondary['region_label']}".strip()
            response_text = f"{response_text}. Also {secondary_prefix}: {secondary['answer']}"
    elif ordered_page_ids:
        response_text = f"Pulled {len(ordered_page_ids)} relevant sheets for review."
    else:
        response_text = "I couldn't find a precise match for that detail."

    if response_text:
        yield {"type": "text", "content": response_text}
        trace.append({"type": "reasoning", "content": response_text})

    # 7) Done
    tokens = _extract_query_tokens(query)
    display_title = " ".join(tokens[:3]).title() if tokens else "Query"

    yield {
        "type": "done",
        "trace": trace,
        "usage": {"inputTokens": 0, "outputTokens": 0},
        "displayTitle": display_title,
        "conversationTitle": display_title,
        "highlights": resolved_highlights,
        "conceptName": None,
        "summary": None,
        "findings": [],
        "crossReferences": [],
        "gaps": [],
    }


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
