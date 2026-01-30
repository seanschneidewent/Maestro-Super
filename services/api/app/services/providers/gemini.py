"""
Gemini AI service for context extraction and agent queries.
"""

import json
import logging
from typing import Any

from google import genai
from google.genai import types

from app.config import get_settings
from app.utils.retry import with_retry

logger = logging.getLogger(__name__)


AGENT_QUERY_PROMPT = '''You are a construction plan assistant. Read the page content from RAG search results and answer the user's question.

PROJECT STRUCTURE:
{project_structure}

PAGE SEARCH RESULTS (with full content):
{page_results}

{history_section}
{viewing_section}
USER QUERY: {query}

Your task:
1. READ the page content carefully to find the answer
2. Select which pages to display to the user
3. Select text to HIGHLIGHT from each page's content (dimensions, specs, labels)
4. Write a brief, helpful response

HIGHLIGHTING GUIDELINES:
- Pick 3-8 most relevant words per page (dimensions, specs, labels that answer the query)
- Use short phrases or exact text snippets from the content when possible

SELECTION GUIDELINES:
- Include ALL pages relevant to the query
- When the query is about a concept (equipment, room, system), also include related schedules/specs/notes pages
- Order pages numerically by sheet number (e.g., E-2.1, E-2.2, E-2.3)
- If search results are empty, look in project structure for relevant pages

RESPONSE STYLE:
You're a helpful secondary superintendent - knowledgeable, casual, and to the point. Talk like a colleague, not a robot.
- Sound natural: "K-201 has the overview, K-211 and K-212 are the enlarged sections."
- Add useful context: "Panel schedule's on E-3.2, but you'll want E-3.1 too for the one-line diagram."
- Be brief: 1-2 sentences max. Superintendents are busy.
- DON'T announce what you did: "I have displayed the pages" ❌
- DON'T sound robotic: "The requested documents are now shown" ❌
- DON'T repeat what the user asked for ❌

TITLE GUIDELINES:
- chat_title: 2-4 word noun phrase for THIS query (e.g., "Electrical Panels", "Kitchen Equipment")
- conversation_title: 2-6 word phrase summarizing the conversation
  - First query: same as chat_title
  - Follow-ups: combine themes (e.g., "Kitchen & Electrical Plans")

Return JSON with this exact structure:
{{
  "page_ids": ["uuid1", "uuid2"],
  "highlights": [
    {{"page_id": "uuid1", "text_matches": ["200A", "MAIN PANEL", "480V"]}},
    {{"page_id": "uuid2", "text_matches": ["3'-6\\"", "GYP. BD."]}}
  ],
  "chat_title": "2-4 word title",
  "conversation_title": "2-6 word title",
  "response": "Brief helpful response"
}}'''

PAGE_SELECTION_PROMPT = '''You are a construction plan assistant. Use the page summaries and extracted details to quickly pick the best pages to verify the user's concept.

PROJECT STRUCTURE:
{project_structure}

PAGE RESULTS (summaries + details):
{page_results}

{history_section}
{viewing_section}
USER QUERY: {query}

Your task:
1. Select the 2-6 most relevant pages for verifying the concept
2. Provide a short verification plan for each selected page (what to look for)
3. Keep it text-only and fast (no image analysis here)

SELECTION GUIDELINES:
- Include ALL pages relevant to the concept (plans, schedules, specs, notes)
- Prefer pages that are likely to contain definitive info (schedules/specs/notes)
- Order pages numerically by sheet number (e.g., E-2.1, E-2.2)

TITLE GUIDELINES:
- chat_title: 2-4 word noun phrase for THIS query (e.g., "Walk-In Cooler")
- conversation_title: 2-6 word phrase summarizing the conversation
  - First query: same as chat_title
  - Follow-ups: combine themes (e.g., "Kitchen & Electrical Plans")

Return JSON with this exact structure:
{{
  "page_ids": ["uuid1", "uuid2"],
  "verification_plan": [
    {{
      "page_id": "uuid1",
      "page_type": "plan|schedule|spec|detail|note",
      "plan": "What to inspect on this page",
      "expected": ["dimensions", "electrical", "notes"]
    }}
  ],
  "chat_title": "2-4 word title",
  "conversation_title": "2-6 word title"
}}'''

VISION_EXPLORATION_PROMPT = '''You are a construction plan specialist with visual analysis and code execution.

You will be given:
- A set of page images (in the SAME ORDER as the manifest below)
- Per-page semantic OCR data (word-level bboxes + roles)
- Per-page context summaries and extracted details
- A verification plan from Phase 1

Your job:
1. Visually inspect each page image as needed to confirm facts.
2. Use code execution to zoom into fine details when needed.
3. Return structured findings with precise references.

IMPORTANT:
- If you can reference semantic OCR word IDs, use "semantic_refs".
- If not, provide a normalized "bbox" as [x0, y0, x1, y1] in 0-1 coordinates.
- Every finding must include page_id, category, content, confidence, and source_text.
- Return gaps for expected-but-not-found information.

PAGE MANIFEST (images provided in same order):
{page_manifest}

VERIFICATION PLAN:
{verification_plan}

{history_section}
{viewing_section}
USER QUERY: {query}

Return JSON with this exact structure:
{{
  "concept_name": "Walk-In Cooler (WIC-1)",
  "summary": "Brief overview",
  "findings": [
    {{
      "category": "location|dimensions|electrical|schedule|spec|detail|note",
      "content": "Human-readable description",
      "page_id": "A2.3",
      "semantic_refs": [142, 143, 144],
      "bbox": [0.45, 0.32, 0.52, 0.35],
      "confidence": "high|medium|verified_via_zoom",
      "source_text": "Actual text read from document"
    }}
  ],
  "cross_references": [
    {{"from_page": "A2.3", "to_page": "E2.1", "relationship": "electrical connection"}}
  ],
  "gaps": [
    "Could not locate refrigerant line routing on mechanical sheets"
  ],
  "response": "Full narrative response..."
}}'''


def _extract_json_response(text: str) -> dict | list:
    """Best-effort JSON extraction for Gemini responses."""
    if not text:
        raise ValueError("Empty response from Gemini")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract first JSON object substring
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        # Fallback: try to extract JSON array substring
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _normalize_vision_result(raw: object) -> dict:
    """Normalize raw vision output into the expected dict shape."""
    if isinstance(raw, list):
        logger.warning("Gemini vision returned list; wrapping into findings[]")
        return {"findings": raw}
    if isinstance(raw, dict):
        return raw
    logger.warning("Gemini vision returned non-dict JSON; coercing to response string")
    return {"response": str(raw)}


def _normalize_selection_result(raw: object) -> dict:
    """Normalize selection output into expected dict shape."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        logger.warning("Gemini selection returned list; coercing to empty selection")
        return {"page_ids": [], "verification_plan": []}
    return {}


async def run_agent_query(
    project_structure: dict[str, Any],
    page_results: list[dict[str, Any]],
    query: str,
    history_context: str = "",
    viewing_context: str = "",
) -> dict[str, Any]:
    """
    Single-shot agent query using Gemini structured JSON output.

    Gemini reads the full page content from RAG and returns:
    - Which pages to display
    - Which text to highlight on each page
    - A brief response

    Args:
        project_structure: Dict with disciplines and pages
        page_results: List of page search results WITH full content
        query: User's question
        history_context: Optional formatted history from previous messages
        viewing_context: Optional context about what page user is viewing

    Returns:
        {
            "page_ids": ["uuid1", "uuid2", ...],
            "highlights": [{"page_id": "uuid1", "text_matches": ["200A", "MAIN PANEL"]}],
            "chat_title": "2-4 word title",
            "conversation_title": "2-6 word title",
            "response": "Brief helpful response"
        }
    """
    try:
        client = _get_gemini_client()

        # Escape curly braces in user input to prevent format string errors
        # (e.g., user query "Show me {A-1}" would crash .format())
        def escape_braces(s: str) -> str:
            return s.replace("{", "{{").replace("}", "}}")

        # Build history section
        history_section = ""
        if history_context:
            history_section = f"CONVERSATION HISTORY:\n{escape_braces(history_context)}\n"

        # Build viewing section
        viewing_section = ""
        if viewing_context:
            viewing_section = f"CURRENT VIEW: {escape_braces(viewing_context)}\n"

        prompt = AGENT_QUERY_PROMPT.format(
            project_structure=json.dumps(project_structure, indent=2),
            page_results=json.dumps(page_results, indent=2),
            query=escape_braces(query),
            history_section=history_section,
            viewing_section=viewing_section,
        )

        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[types.Content(parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
            ),
        )

        result = json.loads(response.text)
        logger.info(f"Gemini agent query complete: {result.get('chat_title', 'Unknown')}")

        # Extract token usage from response metadata
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
            output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0

        # Ensure expected fields exist with defaults (use `or` to handle null values)
        chat_title = result.get("chat_title") or "Query"
        return {
            "page_ids": result.get("page_ids") or [],
            "highlights": result.get("highlights") or [],
            "chat_title": chat_title,
            "conversation_title": result.get("conversation_title") or chat_title,
            "response": result.get("response") or "I found the relevant pages for you.",
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        }

    except Exception as e:
        logger.error(f"Gemini agent query failed: {e}")
        # Re-raise so caller can handle appropriately
        raise


def _get_gemini_client() -> genai.Client:
    """Get Gemini client."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise ValueError("Gemini API key must be configured")
    return genai.Client(api_key=settings.gemini_api_key)


async def select_pages_for_verification(
    project_structure: dict[str, Any],
    page_results: list[dict[str, Any]],
    query: str,
    history_context: str = "",
    viewing_context: str = "",
) -> dict[str, Any]:
    """
    Phase 1: Select candidate pages for verification (text-only).

    Returns:
        {
            "page_ids": [...],
            "verification_plan": [...],
            "chat_title": "...",
            "conversation_title": "...",
            "usage": {...}
        }
    """
    try:
        client = _get_gemini_client()

        def escape_braces(s: str) -> str:
            return s.replace("{", "{{").replace("}", "}}")

        history_section = ""
        if history_context:
            history_section = f"CONVERSATION HISTORY:\n{escape_braces(history_context)}\n"

        viewing_section = ""
        if viewing_context:
            viewing_section = f"CURRENT VIEW: {escape_braces(viewing_context)}\n"

        prompt = PAGE_SELECTION_PROMPT.format(
            project_structure=json.dumps(project_structure, indent=2),
            page_results=json.dumps(page_results, indent=2),
            query=escape_braces(query),
            history_section=history_section,
            viewing_section=viewing_section,
        )

        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[types.Content(parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
            ),
        )

        result = _normalize_selection_result(_extract_json_response(response.text))

        input_tokens = 0
        output_tokens = 0
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
            output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0

        chat_title = result.get("chat_title") or "Query"
        return {
            "page_ids": result.get("page_ids") or [],
            "verification_plan": result.get("verification_plan") or [],
            "chat_title": chat_title,
            "conversation_title": result.get("conversation_title") or chat_title,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        }
    except Exception as e:
        logger.error(f"Gemini page selection failed: {e}")
        raise


async def explore_concept_with_vision(
    query: str,
    pages: list[dict[str, Any]],
    verification_plan: list[dict[str, Any]] | None = None,
    history_context: str = "",
    viewing_context: str = "",
) -> dict[str, Any]:
    """
    Phase 2: Agentic vision exploration with code execution enabled.

    Args:
        pages: List of dicts with image_bytes and metadata for each page.
               Each item should include: page_id, page_name, discipline,
               context_markdown, details, semantic_index (filtered), image_bytes.
    """
    try:
        client = _get_gemini_client()

        def escape_braces(s: str) -> str:
            return s.replace("{", "{{").replace("}", "}}")

        history_section = ""
        if history_context:
            history_section = f"CONVERSATION HISTORY:\n{escape_braces(history_context)}\n"

        viewing_section = ""
        if viewing_context:
            viewing_section = f"CURRENT VIEW: {escape_braces(viewing_context)}\n"

        page_manifest = [
            {
                "page_id": p.get("page_id"),
                "page_name": p.get("page_name"),
                "discipline": p.get("discipline"),
                "context_markdown": p.get("context_markdown"),
                "details": p.get("details"),
                "semantic_index": p.get("semantic_index"),
            }
            for p in pages
        ]

        prompt = VISION_EXPLORATION_PROMPT.format(
            page_manifest=json.dumps(page_manifest, indent=2),
            verification_plan=json.dumps(verification_plan or [], indent=2),
            query=escape_braces(query),
            history_section=history_section,
            viewing_section=viewing_section,
        )

        parts: list[types.Part] = []
        for page in pages:
            image_bytes = page.get("image_bytes")
            if not image_bytes:
                continue
            page_label = f"PAGE IMAGE: {page.get('page_name')} ({page.get('page_id')})"
            parts.append(types.Part.from_text(text=page_label))
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/png"))

        parts.append(types.Part.from_text(text=prompt))

        try:
            code_exec_tool = types.Tool(code_execution=types.ToolCodeExecution)
        except Exception:
            code_exec_tool = types.Tool(code_execution=types.ToolCodeExecution())

        config_kwargs = {
            "response_mime_type": "application/json",
            "tools": [code_exec_tool],
            "media_resolution": "media_resolution_high",
            "temperature": 0,
        }
        try:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level="HIGH")
        except Exception:
            pass

        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[types.Content(parts=parts)],
            config=types.GenerateContentConfig(**config_kwargs),
        )

        result = _normalize_vision_result(_extract_json_response(response.text))

        input_tokens = 0
        output_tokens = 0
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
            output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0

        return {
            "concept_name": result.get("concept_name") or None,
            "summary": result.get("summary") or None,
            "findings": result.get("findings") or [],
            "cross_references": result.get("cross_references") or [],
            "gaps": result.get("gaps") or [],
            "response": result.get("response") or "",
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        }
    except Exception as e:
        logger.error(f"Gemini vision exploration failed: {e}")
        raise


async def _analyze_page_pass_1_impl(
    image_bytes: bytes,
    ocr_text: str,
    ocr_spans: list[dict],
) -> str:
    """Internal implementation of Pass 1 analysis."""
    client = _get_gemini_client()

    # Build prompt with OCR text for better visual+textual understanding
    ocr_section = ""
    if ocr_text:
        ocr_section = f"\n\nOCR-extracted text from this page:\n{ocr_text[:2000]}"  # Limit to prevent token overflow

    prompt = (
        "Describe this construction drawing page briefly. "
        "Include: what type of page it is (floor plan, detail sheet, "
        "elevation, section, schedule, notes, etc.), key elements visible "
        "(keynotes, legends, details, general notes, dimensions, etc.), "
        "and any notable features. Keep it to 2-3 sentences."
        f"{ocr_section}"
    )

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[
            types.Content(
                parts=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                    types.Part.from_text(text=prompt),
                ]
            )
        ],
    )

    result = response.text
    logger.info("Pass 1 analysis complete with Gemini Flash")
    return result


async def analyze_page_pass_1(
    image_bytes: bytes,
    ocr_text: str = "",
    ocr_spans: list[dict] | None = None,
) -> str:
    """
    Pass 1: Analyze a construction drawing page and return initial context summary.

    Uses Gemini 2.0 Flash for fast, cost-effective image analysis.
    Includes retry logic for transient failures.

    Args:
        image_bytes: PNG image bytes of the page
        ocr_text: Full extracted text from Tesseract
        ocr_spans: Word positions for spatial understanding [{text, x, y, w, h, confidence}]

    Returns:
        Initial context summary (2-3 sentences)
    """
    if ocr_spans is None:
        ocr_spans = []

    try:
        return await with_retry(
            _analyze_page_pass_1_impl,
            image_bytes,
            ocr_text,
            ocr_spans,
            max_attempts=3,
            base_delay=1.0,
            exceptions=(Exception,),
        )
    except Exception as e:
        logger.error(f"Gemini Pass 1 analysis failed after retries: {e}")
        raise


async def analyze_pointer(
    image_bytes: bytes,
    page_context: str,
    all_page_names: list[str],
) -> dict:
    """
    Analyze a pointer region with Gemini.

    Args:
        image_bytes: Cropped region PNG bytes
        page_context: Initial context from Pass 1
        all_page_names: List of all page names in project for reference matching

    Returns:
        Dictionary with:
        - title: short descriptive title
        - description: 1-2 paragraph description
        - references: [{target_page, justification}]
        - text_spans: list of extracted text elements
    """
    try:
        client = _get_gemini_client()

        prompt = f"""Analyze this detail from a construction drawing.

Context about this page (from Pass 1 analysis):
{page_context or "(No context available)"}

All pages in this project: {', '.join(all_page_names) if all_page_names else "(No pages available)"}

Tasks:
1. Generate a short, descriptive title for this detail (max 10 words)
2. Write 1-2 paragraphs describing what this detail shows and its purpose
3. Identify ALL references to other pages (e.g., "See S2.01", "Detail 3/A1.02", "Refer to Structural")
   - For each reference, provide the target page name and the text that justifies it
   - Only include references if the target page exists in the project list
4. Extract ALL visible text from the image as individual text spans

Return JSON:
{{
  "title": "short descriptive title",
  "description": "1-2 paragraph description",
  "references": [
    {{"target_page": "page_name", "justification": "the text mentioning this reference"}}
  ],
  "text_spans": ["all", "visible", "text", "elements"]
}}"""

        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[
                types.Content(
                    parts=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                        types.Part.from_text(text=prompt),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )

        result = json.loads(response.text)
        logger.info(f"Pointer analysis complete: {result.get('title', 'Unknown')}")
        return result

    except Exception as e:
        logger.error(f"Gemini pointer analysis failed: {e}")
        # Return fallback response on failure
        return {
            "title": "Analysis Failed",
            "description": f"Unable to analyze this region. Error: {str(e)}",
            "references": [],
            "text_spans": [],
        }
