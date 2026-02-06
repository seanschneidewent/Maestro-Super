"""Re-grounding service for Learning-triggered vision fixes."""

from __future__ import annotations

import asyncio
import json
import logging
from io import BytesIO
from typing import Any
from uuid import uuid4

from google import genai
from google.genai import types
from PIL import Image
from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.models.page import Page
from app.models.pointer import Pointer
from app.services.providers.gemini import normalize_bbox
from app.services.providers.pdf_renderer import pdf_page_to_image
from app.services.utils.parsing import extract_json_response
from app.services.utils.storage import download_file, upload_snapshot

logger = logging.getLogger(__name__)


REGROUND_PROMPT = """You are a construction drawing analyst tasked with re-grounding a page.

INSTRUCTION:
{instruction}

PAGE CONTEXT:
- Page name: {page_name}
- Existing pointer boxes (already known): {existing_pointers}

TASK:
1. Re-analyze the page image.
2. Identify missing or incorrect regions based on the instruction.
3. Return NEW bounding boxes only (do not repeat existing pointers).
4. Use code execution to inspect and crop/zoom if needed.

Return JSON with this structure:
{{
  "new_pointers": [
    {{
      "title": "Short label for the region",
      "bbox": [x0, y0, x1, y1],
      "notes": "Optional notes about what this region contains"
    }}
  ]
}}

Bounding box coordinates can be normalized (0-1) or pixel-based.
"""


def _extract_text_response(response: Any) -> str:
    text = getattr(response, "text", "") or ""
    if text:
        return text

    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return ""

    content = getattr(candidates[0], "content", None)
    if not content:
        return ""

    parts = getattr(content, "parts", None) or []
    for part in parts:
        if getattr(part, "thought", False):
            continue
        piece = getattr(part, "text", None)
        if piece:
            text += piece
    return text


def _safe_title(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


async def trigger_reground(
    page_id: str,
    instruction: str,
    db: DBSession,
) -> list[str]:
    """
    Spawn Gemini to re-analyze a page and create new Pointer rows.

    Returns list of new pointer IDs.
    """
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise ValueError("Page not found")

    image_path = page.page_image_path or page.file_path
    if not image_path:
        raise ValueError("Page image not available for re-ground")

    pointers = db.query(Pointer).filter(Pointer.page_id == page_id).all()
    existing = [
        {
            "pointer_id": p.id,
            "title": p.title,
            "bbox": {
                "x0": p.bbox_x,
                "y0": p.bbox_y,
                "x1": p.bbox_x + p.bbox_width,
                "y1": p.bbox_y + p.bbox_height,
            },
        }
        for p in pointers
    ]

    image_bytes = await download_file(image_path)
    if not page.page_image_path and image_path.lower().endswith(".pdf"):
        image_bytes = await asyncio.to_thread(
            pdf_page_to_image,
            image_bytes,
            page_index=page.page_index or 0,
        )

    settings = get_settings()
    if not settings.gemini_api_key:
        raise ValueError("Gemini API key must be configured")

    client = genai.Client(api_key=settings.gemini_api_key)

    prompt = REGROUND_PROMPT.format(
        instruction=instruction or "Re-ground the page for missing or incorrect regions.",
        page_name=page.page_name or "Unknown",
        existing_pointers=json.dumps(existing, indent=2),
    )

    try:
        code_exec_tool = types.Tool(code_execution=types.ToolCodeExecution)
    except Exception:
        code_exec_tool = types.Tool(code_execution=types.ToolCodeExecution())

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
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            tools=[code_exec_tool],
            temperature=0,
        ),
    )

    response_text = _extract_text_response(response)
    if not response_text:
        logger.warning("Re-ground returned empty response for page %s", page_id)
        return []

    result = extract_json_response(response_text)
    new_regions = result.get("new_pointers") or []
    if not isinstance(new_regions, list):
        logger.warning("Re-ground response missing new_pointers list for page %s", page_id)
        return []

    image = Image.open(BytesIO(image_bytes))
    width, height = image.size

    created_ids: list[str] = []

    for idx, region in enumerate(new_regions, start=1):
        if not isinstance(region, dict):
            continue

        bbox_raw = region.get("bbox")
        if not bbox_raw:
            continue

        normalized = normalize_bbox(bbox_raw, width=width, height=height)
        if normalized["x1"] <= normalized["x0"] or normalized["y1"] <= normalized["y0"]:
            continue

        left = int(normalized["x0"] * width)
        top = int(normalized["y0"] * height)
        right = int(normalized["x1"] * width)
        bottom = int(normalized["y1"] * height)
        if right <= left or bottom <= top:
            continue

        cropped = image.crop((left, top, right, bottom))
        buffer = BytesIO()
        cropped.save(buffer, format="PNG")
        cropped_bytes = buffer.getvalue()

        pointer_id = str(uuid4())
        png_path = await upload_snapshot(cropped_bytes, pointer_id, user_id="learning")

        title = _safe_title(region.get("title"), f"Re-grounded region {idx}")
        description = _safe_title(region.get("notes"), "Pending enrichment from re-ground.")

        pointer = Pointer(
            id=pointer_id,
            page_id=page_id,
            title=title,
            description=description,
            text_spans=[],
            ocr_data=None,
            bbox_x=normalized["x0"],
            bbox_y=normalized["y0"],
            bbox_width=normalized["x1"] - normalized["x0"],
            bbox_height=normalized["y1"] - normalized["y0"],
            png_path=png_path,
            needs_embedding=True,
            enrichment_status="pending",
            enrichment_metadata={
                "reground_instruction": instruction,
                "regrounded_at": "now",
            },
        )
        db.add(pointer)
        created_ids.append(pointer_id)

    if created_ids:
        db.commit()
        logger.info("Re-ground created %d new pointers on page %s", len(created_ids), page_id)

    return created_ids
