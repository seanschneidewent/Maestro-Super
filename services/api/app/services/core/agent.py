"""Query agent for navigating construction plan graph.

Fast mode routes users to likely pages using RAG + project structure context.
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

logger = logging.getLogger(__name__)

FAST_PAGE_LIMIT = 8
DEEP_PAGE_LIMIT = 5
CROSS_REF_PAGE_LIMIT = 3
DEEP_CANDIDATE_REGION_LIMIT = 8


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
) -> tuple[list[str], dict[str, Page]]:
    """Sort selected pages by sheet number and return a lookup map."""
    if not page_ids:
        return [], {}

    pages_for_order = _load_pages_for_vision(db, page_ids)
    page_map = {str(p.id): p for p in pages_for_order}
    ordered_page_ids = sorted(
        [pid for pid in page_ids if pid in page_map],
        key=lambda pid: _page_sort_key(page_map[pid].page_name or ""),
    )
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
    mode: Literal["fast", "deep"] = "fast",
) -> AsyncIterator[dict]:
    """
    Execute agent query with streaming events.

    Modes:
    - fast (default): RAG + project structure routing (no vision calls)
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
        mode: "fast" or "deep"
    """
    mode = "deep" if mode == "deep" else "fast"
    backend = os.environ.get("AGENT_BACKEND", "gemini").lower()

    if mode == "deep":
        async for event in run_agent_query_deep(
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
    - Use RAG to identify likely pages
    - Route user to those pages without running vision inference
    """
    from app.services.tools import get_project_structure_summary, search_pages, select_pages
    from app.services.utils.search import search_pages_and_regions

    _ = history_messages, viewing_context

    trace: list[dict] = []

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

    # 3) Secondary keyword search to improve routing confidence
    yield {"type": "tool_call", "tool": "search_pages", "input": {"query": query}}
    trace.append({"type": "tool_call", "tool": "search_pages", "input": {"query": query}})
    page_results = await search_pages(db, query=query, project_id=project_id, limit=FAST_PAGE_LIMIT)
    yield {"type": "tool_result", "tool": "search_pages", "result": page_results}
    trace.append({"type": "tool_result", "tool": "search_pages", "result": page_results})

    region_page_ids = [pid for pid in region_matches.keys() if pid]
    keyword_page_ids = [p.get("page_id") for p in page_results if p.get("page_id")]

    page_ids = list(dict.fromkeys([*region_page_ids, *keyword_page_ids]))

    if not page_ids:
        # Last fallback: choose a few sheets from project structure if available.
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
                    if len(page_ids) >= FAST_PAGE_LIMIT:
                        break
                if len(page_ids) >= FAST_PAGE_LIMIT:
                    break

    if page_ids:
        page_ids = _expand_with_cross_reference_pages(db, project_id, page_ids)

    page_ids = list(dict.fromkeys([pid for pid in page_ids if pid]))[:FAST_PAGE_LIMIT]
    ordered_page_ids, page_map = _order_page_ids(db, page_ids)

    # 4) Select pages for frontend display
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

    # 5) Compose response text
    if ordered_page_ids:
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
    else:
        response_text = "I couldn't find a strong page match yet. Try adding a sheet number or discipline keyword."

    if response_text:
        yield {"type": "text", "content": response_text}
        trace.append({"type": "reasoning", "content": response_text})

    # 6) Done
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
    from app.services.tools import get_project_structure_summary, search_pages, select_pages
    from app.services.utils.search import search_pages_and_regions

    trace: list[dict] = []

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

    # 4) Select pages so frontend and persistence stay consistent
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

    vision_page_ids = [str(p.get("page_id")) for p in pages_for_vision if p.get("page_id")]
    tool_input = {"query": query, "page_ids": vision_page_ids}
    yield {"type": "tool_call", "tool": "explore_concept_with_vision", "input": tool_input}
    trace.append({"type": "tool_call", "tool": "explore_concept_with_vision", "input": tool_input})

    concept_result: dict[str, Any] = {}
    try:
        async for event in explore_concept_with_vision_streaming(
            query=query,
            pages=pages_for_vision,
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
        logger.exception("Deep vision exploration failed: %s", e)
        yield {"type": "error", "message": f"Deep analysis failed: {str(e)}"}
        return

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

    usage_raw = concept_result.get("usage") if isinstance(concept_result.get("usage"), dict) else {}

    def _to_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    input_tokens = _to_int(usage_raw.get("input_tokens") or usage_raw.get("inputTokens"))
    output_tokens = _to_int(usage_raw.get("output_tokens") or usage_raw.get("outputTokens"))

    concept_name = concept_result.get("concept_name")
    if not isinstance(concept_name, str):
        concept_name = None
    summary = concept_result.get("summary")
    if not isinstance(summary, str):
        summary = None
    findings = concept_result.get("findings") if isinstance(concept_result.get("findings"), list) else []
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
