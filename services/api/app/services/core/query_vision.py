"""
Query-time agentic vision: zoom into relevant regions and extract precise details.
"""

from __future__ import annotations

import logging
from io import BytesIO

from PIL import Image
from google import genai
from google.genai import types

from app.config import get_settings, QUERY_VISION_MODEL
from app.services.utils.parsing import extract_json_response

logger = logging.getLogger(__name__)


def _get_gemini_client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise ValueError("Gemini API key must be configured")
    return genai.Client(api_key=settings.gemini_api_key)


def _build_query_prompt(
    question: str,
    region_type: str,
    region_label: str,
    page_name: str,
    sheet_reflection: str,
) -> str:
    lines = [
        "You are examining a specific region of a construction drawing.",
        "",
        f"USER QUESTION: {question}",
        "",
        "REGION CONTEXT:",
        f"- Type: {region_type}",
        f"- Label: {region_label}",
        f"- Sheet: {page_name}",
        "",
        "SHEET CONTEXT:",
        sheet_reflection or "",
        "",
        "## YOUR TASK",
        "",
        "1. Answer the question using what you see in this region",
        "2. Extract precise bounding boxes for elements to highlight",
        "3. Note any dimensions, specs, or notes relevant to the answer",
        "",
        "## OUTPUT FORMAT",
        "",
        "{",
        '  "answer": "Direct answer to the question",',
        '  "elements": [',
        "    {",
        '      "text": "2-1/2\\"",',
        '      "bbox": {"x0": int, "y0": int, "x1": int, "y1": int},',
        '      "role": "dimension|material|note|label"',
        "    }",
        "  ],",
        '  "confidence": "high|medium|low",',
        '  "related_info": "Any additional relevant context"',
        "}",
        "",
        "Note: Bounding boxes are relative to the cropped region image.",
    ]
    return "\n".join(lines)


def crop_region(image_bytes: bytes, bbox: dict, padding: int = 50) -> tuple[bytes, dict]:
    """Crop image to region bbox with padding. Returns (bytes, crop_bbox)."""
    image = Image.open(BytesIO(image_bytes))
    raw_x0 = bbox.get("x0", 0) if isinstance(bbox, dict) else 0
    raw_y0 = bbox.get("y0", 0) if isinstance(bbox, dict) else 0
    raw_x1 = bbox.get("x1", 0) if isinstance(bbox, dict) else 0
    raw_y1 = bbox.get("y1", 0) if isinstance(bbox, dict) else 0

    def as_float(value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    x0 = as_float(raw_x0)
    y0 = as_float(raw_y0)
    x1 = as_float(raw_x1)
    y1 = as_float(raw_y1)

    # Brain Mode stores normalized coordinates (0-1). Keep pixel fallback for older data.
    coords = [x0, y0, x1, y1]
    if all(0.0 <= coord <= 1.0 for coord in coords):
        x0 = x0 * image.width
        x1 = x1 * image.width
        y0 = y0 * image.height
        y1 = y1 * image.height

    x0 = int(round(x0))
    y0 = int(round(y0))
    x1 = int(round(x1))
    y1 = int(round(y1))

    x0 = max(0, x0 - padding)
    y0 = max(0, y0 - padding)
    x1 = min(image.width, x1 + padding)
    y1 = min(image.height, y1 + padding)

    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0

    cropped = image.crop((x0, y0, x1, y1))
    buffer = BytesIO()
    cropped.save(buffer, format="PNG")
    return buffer.getvalue(), {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


async def query_with_vision(
    question: str,
    page_image_bytes: bytes,
    relevant_regions: list[dict],
    page_context: str,
    page_name: str = "Unknown",
) -> dict:
    """
    Query-time agentic vision: zoom into regions, extract details.

    Args:
        question: User's question
        page_image_bytes: Cropped region PNG bytes
        relevant_regions: Regions to examine (from vector search)
        page_context: Sheet reflection for context
        page_name: Sheet name for prompt context
    """
    if not relevant_regions:
        raise ValueError("relevant_regions is required for query-time vision")

    region = relevant_regions[0] or {}
    region_type = str(region.get("type") or "unknown")
    region_label = str(region.get("label") or "")

    prompt = _build_query_prompt(
        question=question,
        region_type=region_type,
        region_label=region_label,
        page_name=page_name,
        sheet_reflection=page_context,
    )

    client = _get_gemini_client()
    response = client.models.generate_content(
        model=QUERY_VISION_MODEL,
        contents=[
            types.Content(
                parts=[
                    types.Part.from_bytes(data=page_image_bytes, mime_type="image/png"),
                    types.Part.from_text(text=prompt),
                ]
            )
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0,
            media_resolution="media_resolution_high",
        ),
    )

    result = extract_json_response(response.text)

    if not isinstance(result, dict):
        result = {}

    answer = result.get("answer") if isinstance(result.get("answer"), str) else ""
    elements = result.get("elements") if isinstance(result.get("elements"), list) else []
    confidence = result.get("confidence") if isinstance(result.get("confidence"), str) else "low"
    related_info = result.get("related_info") if isinstance(result.get("related_info"), str) else ""

    logger.info(
        "[Query Vision] %s region '%s': %s elements",
        page_name,
        region_label or region_type,
        len(elements),
    )

    return {
        "answer": answer,
        "elements": elements,
        "confidence": confidence,
        "related_info": related_info,
    }
