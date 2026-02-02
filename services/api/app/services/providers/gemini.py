"""
Gemini AI service for context extraction and agent queries.
"""

import json
import logging
import re
import time
from typing import Any, AsyncIterator

from google import genai
from google.genai import types

from app.config import AGENT_QUERY_MODEL, get_settings
from app.services.prompts import BRAIN_MODE_PROMPT_V4
from app.services.utils.parsing import extract_json_response
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
- Per-page Brain Mode regions with bounding boxes
- Per-page candidate_regions ranked by RAG relevance to the user query
- A verification plan from Phase 1

Your job:
1. Start with candidate_regions first (these are the best RAG hints).
2. Decide which regions to inspect in detail and use code execution to zoom/crop.
3. Expand to other page regions only if candidate_regions are insufficient.
4. Return structured findings with precise references.

IMPORTANT:
- candidate_regions and regions include normalized bboxes (0-1) and metadata (type/label/detailNumber/regionIndex).
- For each finding, `page_id` must exactly match one of the `page_id` values in PAGE MANIFEST (do not use page names here).
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

def _extract_json_response(text: str) -> dict[str, Any]:
    """Extract JSON from model output, including markdown code blocks."""
    if not text:
        raise ValueError("Empty response from Gemini")

    code_block_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if code_block_match:
        text = code_block_match.group(1)

    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError("Could not extract valid JSON from response")


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_bbox(bbox: Any, width: int, height: int) -> dict[str, float]:
    """
    Normalize bounding box coordinates to 0-1 and clamp to image bounds.

    Supports:
    - Dict format: {"x0": ..., "y0": ..., "x1": ..., "y1": ...}
    - List/tuple format: [x0, y0, x1, y1]
    - Values already normalized (0-1), normalized to 1000, or pixel-based
    """
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        raw_x0, raw_y0, raw_x1, raw_y1 = bbox
    elif isinstance(bbox, dict):
        raw_x0 = bbox.get("x0", 0)
        raw_y0 = bbox.get("y0", 0)
        raw_x1 = bbox.get("x1", 0)
        raw_y1 = bbox.get("y1", 0)
    else:
        raw_x0 = raw_y0 = raw_x1 = raw_y1 = 0

    x0 = _coerce_float(raw_x0)
    y0 = _coerce_float(raw_y0)
    x1 = _coerce_float(raw_x1)
    y1 = _coerce_float(raw_y1)

    def to_unit(value: float, dimension: int) -> float:
        abs_value = abs(value)
        if abs_value <= 1.0:
            return value
        if abs_value <= 1000.0:
            return value / 1000.0
        if dimension > 0:
            return value / float(dimension)
        return 0.0

    x0 = to_unit(x0, width)
    x1 = to_unit(x1, width)
    y0 = to_unit(y0, height)
    y1 = to_unit(y1, height)

    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0

    x0 = max(0.0, min(1.0, x0))
    y0 = max(0.0, min(1.0, y0))
    x1 = max(0.0, min(1.0, x1))
    y1 = max(0.0, min(1.0, y1))
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def _to_bbox_corners(raw_bbox: Any) -> list[float] | None:
    """Convert supported bbox shapes to [x0, y0, x1, y1]."""
    if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 4:
        return [
            _coerce_float(raw_bbox[0]),
            _coerce_float(raw_bbox[1]),
            _coerce_float(raw_bbox[2]),
            _coerce_float(raw_bbox[3]),
        ]

    if not isinstance(raw_bbox, dict):
        return None

    if all(key in raw_bbox for key in ("x0", "y0", "x1", "y1")):
        return [
            _coerce_float(raw_bbox.get("x0")),
            _coerce_float(raw_bbox.get("y0")),
            _coerce_float(raw_bbox.get("x1")),
            _coerce_float(raw_bbox.get("y1")),
        ]

    if all(key in raw_bbox for key in ("left", "top", "right", "bottom")):
        return [
            _coerce_float(raw_bbox.get("left")),
            _coerce_float(raw_bbox.get("top")),
            _coerce_float(raw_bbox.get("right")),
            _coerce_float(raw_bbox.get("bottom")),
        ]

    if all(key in raw_bbox for key in ("x", "y", "width", "height")):
        x = _coerce_float(raw_bbox.get("x"))
        y = _coerce_float(raw_bbox.get("y"))
        w = _coerce_float(raw_bbox.get("width"))
        h = _coerce_float(raw_bbox.get("height"))
        return [x, y, x + w, y + h]

    if all(key in raw_bbox for key in ("left", "top", "width", "height")):
        x = _coerce_float(raw_bbox.get("left"))
        y = _coerce_float(raw_bbox.get("top"))
        w = _coerce_float(raw_bbox.get("width"))
        h = _coerce_float(raw_bbox.get("height"))
        return [x, y, x + w, y + h]

    return None


def _normalize_ref(ref: Any) -> int | str | None:
    if ref is None:
        return None
    if isinstance(ref, bool):
        return None
    if isinstance(ref, int):
        return ref
    if isinstance(ref, float):
        if ref.is_integer():
            return int(ref)
        return None
    if isinstance(ref, str):
        value = ref.strip()
        if not value:
            return None
        if value.isdigit():
            return int(value)
        return value
    return None


def _normalize_refs(raw_refs: Any) -> list[int | str]:
    if not isinstance(raw_refs, list):
        return []
    normalized: list[int | str] = []
    for ref in raw_refs:
        parsed = _normalize_ref(ref)
        if parsed is not None:
            normalized.append(parsed)
    return normalized


def _canonical_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def normalize_vision_findings(
    findings: Any,
    pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Normalize deep-vision finding payloads for UI overlays.

    - Ensures `page_id` maps to known selected pages (id or page-name aliases).
    - Normalizes bbox units to 0-1 (supports normalized, 0-1000, or pixel-ish coords).
    - Derives bbox from `semantic_refs` when explicit bbox is missing.
    """
    if not isinstance(findings, list):
        return []

    page_alias_to_id: dict[str, str] = {}
    page_name_by_id: dict[str, str] = {}
    page_size_by_id: dict[str, tuple[int, int]] = {}
    word_bbox_by_page: dict[str, dict[str, dict[str, float]]] = {}

    for page in pages:
        if not isinstance(page, dict):
            continue

        page_id = str(page.get("page_id") or "").strip()
        if not page_id:
            continue

        page_name = str(page.get("page_name") or "").strip()
        page_name_by_id[page_id] = page_name

        page_alias_to_id[_canonical_key(page_id)] = page_id
        if page_name:
            page_alias_to_id[_canonical_key(page_name)] = page_id

        semantic_index = page.get("semantic_index")
        if not isinstance(semantic_index, dict):
            semantic_index = {}

        width = int(round(_coerce_float(semantic_index.get("image_width"), 0)))
        height = int(round(_coerce_float(semantic_index.get("image_height"), 0)))
        page_size_by_id[page_id] = (max(width, 0), max(height, 0))

        words = semantic_index.get("words")
        if not isinstance(words, list):
            words = []

        word_bbox_map: dict[str, dict[str, float]] = {}
        for word in words:
            if not isinstance(word, dict):
                continue
            word_id = _normalize_ref(word.get("id"))
            if word_id is None:
                continue

            bbox_corners = _to_bbox_corners(word.get("bbox"))
            if not bbox_corners:
                continue

            bbox = normalize_bbox(bbox_corners, width=width, height=height)
            if bbox["x1"] <= bbox["x0"] or bbox["y1"] <= bbox["y0"]:
                continue

            word_bbox_map[str(word_id)] = bbox

        word_bbox_by_page[page_id] = word_bbox_map

    normalized_findings: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue

        raw_page = (
            finding.get("page_id")
            or finding.get("pageId")
            or finding.get("page_name")
            or finding.get("pageName")
            or ""
        )
        raw_page_str = str(raw_page).strip()
        page_id = page_alias_to_id.get(_canonical_key(raw_page_str), raw_page_str)

        width, height = page_size_by_id.get(page_id, (0, 0))
        refs = _normalize_refs(finding.get("semantic_refs") or finding.get("semanticRefs") or [])

        normalized_bbox: dict[str, float] | None = None
        bbox_corners = _to_bbox_corners(finding.get("bbox"))
        if bbox_corners:
            candidate_bbox = normalize_bbox(bbox_corners, width=width, height=height)
            if candidate_bbox["x1"] > candidate_bbox["x0"] and candidate_bbox["y1"] > candidate_bbox["y0"]:
                normalized_bbox = candidate_bbox

        if normalized_bbox is None and refs:
            word_bboxes = word_bbox_by_page.get(page_id, {})
            ref_bboxes = [word_bboxes.get(str(ref)) for ref in refs]
            ref_bboxes = [bbox for bbox in ref_bboxes if bbox is not None]
            if ref_bboxes:
                normalized_bbox = {
                    "x0": min(bbox["x0"] for bbox in ref_bboxes),
                    "y0": min(bbox["y0"] for bbox in ref_bboxes),
                    "x1": max(bbox["x1"] for bbox in ref_bboxes),
                    "y1": max(bbox["y1"] for bbox in ref_bboxes),
                }

        category = str(finding.get("category") or "")
        content = str(finding.get("content") or "").strip()
        confidence_raw = finding.get("confidence")
        source_text_raw = finding.get("source_text", finding.get("sourceText"))
        page_name_raw = finding.get("page_name", finding.get("pageName"))

        output: dict[str, Any] = {
            "category": category,
            "content": content,
            "page_id": page_id,
        }

        if refs:
            output["semantic_refs"] = refs
        if normalized_bbox is not None:
            output["bbox"] = [
                normalized_bbox["x0"],
                normalized_bbox["y0"],
                normalized_bbox["x1"],
                normalized_bbox["y1"],
            ]
        if isinstance(confidence_raw, str) and confidence_raw:
            output["confidence"] = confidence_raw
        if isinstance(source_text_raw, str) and source_text_raw:
            output["source_text"] = source_text_raw

        page_name = str(page_name_raw or "").strip() or page_name_by_id.get(page_id, "")
        if page_name:
            output["page_name"] = page_name

        if output["content"] and output["page_id"]:
            normalized_findings.append(output)

    return normalized_findings


def process_brain_mode_result(result: dict[str, Any], width: int, height: int) -> dict[str, Any]:
    """Normalize Brain Mode result structure for storage and downstream use."""
    regions = result.get("regions", [])
    if not isinstance(regions, list):
        regions = []

    normalized_regions: list[dict[str, Any]] = []
    for idx, region in enumerate(regions):
        if not isinstance(region, dict):
            continue

        normalized = dict(region)
        normalized["id"] = region.get("id") or f"region_{idx + 1:03d}"
        normalized["type"] = str(region.get("type") or "unknown").lower()
        normalized["bbox"] = normalize_bbox(region.get("bbox", {}), width, height)
        normalized["label"] = region.get("label") or region.get("name") or ""
        normalized["confidence"] = _coerce_float(region.get("confidence"), 0.0)

        detail_number = region.get("detail_number")
        if detail_number is not None:
            normalized["detail_number"] = str(detail_number)

        normalized_regions.append(normalized)

    sheet_reflection = result.get("sheet_reflection", "")
    if not isinstance(sheet_reflection, str):
        sheet_reflection = ""

    page_type = result.get("page_type", "unknown")
    if not isinstance(page_type, str):
        page_type = "unknown"

    cross_refs = result.get("cross_references", [])
    if not isinstance(cross_refs, list):
        cross_refs = []
    normalized_cross_refs = []
    for cross_ref in cross_refs:
        if isinstance(cross_ref, dict):
            sheet_name = cross_ref.get("sheet")
            if sheet_name:
                normalized_cross_refs.append(str(sheet_name))
        elif cross_ref:
            normalized_cross_refs.append(str(cross_ref))

    sheet_info = result.get("sheet_info", {})
    if not isinstance(sheet_info, dict):
        sheet_info = {}

    index = result.get("index", {})
    if not isinstance(index, dict):
        index = {}

    questions = result.get("questions_this_sheet_answers", [])
    if not isinstance(questions, list):
        questions = []

    return {
        "regions": normalized_regions,
        "sheet_reflection": sheet_reflection,
        "page_type": page_type,
        "discipline": str(result.get("discipline") or ""),
        "cross_references": normalized_cross_refs,
        "sheet_info": sheet_info,
        "index": index,
        "questions_this_sheet_answers": [str(q) for q in questions if q],
    }


def validate_brain_mode_response(result: dict[str, Any]) -> bool:
    """Validate minimum required response structure from Brain Mode analysis."""
    if not isinstance(result, dict):
        return False
    required_keys = ["regions", "sheet_info", "index"]
    return all(key in result for key in required_keys)


async def analyze_sheet_brain_mode(
    image_bytes: bytes,
    page_name: str,
    discipline: str,
    custom_prompt: str | None = None,
) -> tuple[dict[str, Any], int]:
    """
    Single Gemini call for Brain Mode comprehension.

    Returns:
        (result_dict, processing_time_ms)
    """
    start_time = time.time()

    try:
        settings = get_settings()
        client = _get_gemini_client()

        prompt_text = custom_prompt or BRAIN_MODE_PROMPT_V4
        prompt = (
            f"{prompt_text}\n\n"
            f"PAGE NAME: {page_name}\n"
            f"DISCIPLINE: {discipline}"
        )

        config_kwargs: dict[str, Any] = {
            "response_mime_type": "application/json",
            "temperature": 0,
            "media_resolution": "media_resolution_high",
        }

        if settings.use_agentic_vision:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=settings.brain_mode_thinking_level
            )
            try:
                code_exec_tool = types.Tool(code_execution=types.ToolCodeExecution)
            except Exception:
                code_exec_tool = types.Tool(code_execution=types.ToolCodeExecution())
            config_kwargs["tools"] = [code_exec_tool]

        response = client.models.generate_content(
            model=settings.brain_mode_model,
            contents=[
                types.Content(
                    parts=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                        types.Part.from_text(text=prompt),
                    ]
                )
            ],
            config=types.GenerateContentConfig(**config_kwargs),
        )

        response_text = ""
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            content = getattr(candidates[0], "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                if getattr(part, "thought", False):
                    continue
                text = getattr(part, "text", None)
                if text:
                    response_text += text
        if not response_text:
            response_text = getattr(response, "text", "") or ""

        result = _extract_json_response(response_text)
        if not validate_brain_mode_response(result):
            raise ValueError("Invalid response structure")

        image_width = _coerce_float(result.get("image_width"), 0.0)
        image_height = _coerce_float(result.get("image_height"), 0.0)
        if image_width <= 0 or image_height <= 0:
            from io import BytesIO

            from PIL import Image

            image = Image.open(BytesIO(image_bytes))
            image_width, image_height = image.size

        processed_result = process_brain_mode_result(
            result,
            width=int(image_width),
            height=int(image_height),
        )

        timing_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "Brain Mode analysis complete for %s in %sms (agentic_vision=%s)",
            page_name,
            timing_ms,
            settings.use_agentic_vision,
        )
        return processed_result, timing_ms

    except Exception as e:
        logger.error(f"Brain mode processing failed: {e}")
        raise


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
            model=AGENT_QUERY_MODEL,
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
            model=AGENT_QUERY_MODEL,
            contents=[types.Content(parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
            ),
        )

        result = extract_json_response(response.text)

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
                "regions": p.get("regions"),
                "candidate_regions": p.get("candidate_regions"),
                "master_index": p.get("master_index"),
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
            model=AGENT_QUERY_MODEL,
            contents=[types.Content(parts=parts)],
            config=types.GenerateContentConfig(**config_kwargs),
        )

        result = extract_json_response(response.text)
        normalized_findings = normalize_vision_findings(result.get("findings"), pages)

        input_tokens = 0
        output_tokens = 0
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
            output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0

        return {
            "concept_name": result.get("concept_name") or None,
            "summary": result.get("summary") or None,
            "findings": normalized_findings,
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


async def explore_concept_with_vision_streaming(
    query: str,
    pages: list[dict[str, Any]],
    verification_plan: list[dict[str, Any]] | None = None,
    history_context: str = "",
    viewing_context: str = "",
) -> AsyncIterator[dict[str, Any]]:
    """
    Phase 2: Agentic vision exploration with streaming thoughts.

    Yields:
        {"type": "thinking", "content": "..."} for thought chunks
        {"type": "result", "data": {...}} once final JSON is parsed
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
                "regions": p.get("regions"),
                "candidate_regions": p.get("candidate_regions"),
                "master_index": p.get("master_index"),
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
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level="HIGH",
                include_thoughts=True,
            )
        except Exception:
            try:
                config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level="HIGH")
            except Exception:
                pass

        stream = client.models.generate_content_stream(
            model=AGENT_QUERY_MODEL,
            contents=[types.Content(parts=parts)],
            config=types.GenerateContentConfig(**config_kwargs),
        )

        accumulated_text = ""
        usage_metadata = None

        for chunk in stream:
            if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                usage_metadata = chunk.usage_metadata

            candidates = getattr(chunk, "candidates", None) or []
            if not candidates:
                continue

            content = getattr(candidates[0], "content", None)
            if not content:
                continue

            for part in getattr(content, "parts", []) or []:
                text = getattr(part, "text", None)
                if not text:
                    continue
                if getattr(part, "thought", False):
                    yield {"type": "thinking", "content": text}
                else:
                    accumulated_text += text

        result = extract_json_response(accumulated_text)
        normalized_findings = normalize_vision_findings(result.get("findings"), pages)

        input_tokens = 0
        output_tokens = 0
        if usage_metadata:
            input_tokens = getattr(usage_metadata, "prompt_token_count", 0) or 0
            output_tokens = getattr(usage_metadata, "candidates_token_count", 0) or 0

        yield {
            "type": "result",
            "data": {
                "concept_name": result.get("concept_name") or None,
                "summary": result.get("summary") or None,
                "findings": normalized_findings,
                "cross_references": result.get("cross_references") or [],
                "gaps": result.get("gaps") or [],
                "response": result.get("response") or "",
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            },
        }
    except Exception as e:
        logger.error(f"Gemini vision exploration streaming failed: {e}")
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
        model=AGENT_QUERY_MODEL,
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
            model=AGENT_QUERY_MODEL,
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
