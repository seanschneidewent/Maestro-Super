"""
Brain Mode Processor - single-pass sheet comprehension.

Generates page structure regions and a superintendent-style reflection
to power query-time precision.
"""

from __future__ import annotations

import logging
import time
from io import BytesIO

from PIL import Image

from app.services.providers.gemini import analyze_sheet_brain_mode
from app.services.utils.parsing import coerce_int
from app.utils.retry import with_retry

logger = logging.getLogger(__name__)


def _normalize_bbox(bbox: dict, width: int, height: int) -> dict:
    x0 = coerce_int(bbox.get("x0"), 0)
    y0 = coerce_int(bbox.get("y0"), 0)
    x1 = coerce_int(bbox.get("x1"), 0)
    y1 = coerce_int(bbox.get("y1"), 0)

    x0 = max(0, min(width, x0))
    y0 = max(0, min(height, y0))
    x1 = max(0, min(width, x1))
    y1 = max(0, min(height, y1))

    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0

    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


async def process_page_brain_mode(
    image_bytes: bytes,
    page_name: str,
    discipline_name: str,
) -> dict:
    """
    Brain Mode: Comprehend the sheet structure.

    Returns:
        {
            "regions": [...],           # Structural bboxes
            "sheet_reflection": "...",  # Intelligent markdown
            "page_type": "detail_sheet",
            "cross_references": ["S-101", "S-201"],
        }
    """
    if not image_bytes:
        raise ValueError("image_bytes is required for Brain Mode processing")

    image = Image.open(BytesIO(image_bytes))
    width, height = image.size

    # Brain Mode analysis with retry logic and timing
    start_time = time.perf_counter()
    result = await with_retry(
        analyze_sheet_brain_mode,
        image_bytes=image_bytes,
        page_name=page_name,
        discipline=discipline_name,
        max_attempts=3,
        base_delay=1.0,
        exceptions=(Exception,),
    )
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info("[Brain Mode] %s: analysis completed in %.0fms", page_name, elapsed_ms)

    regions = result.get("regions") if isinstance(result, dict) else None
    if not isinstance(regions, list):
        regions = []

    normalized_regions = []
    for idx, region in enumerate(regions):
        if not isinstance(region, dict):
            continue
        bbox = region.get("bbox") or {}
        normalized = {
            "id": region.get("id") or f"region_{idx + 1:03d}",
            "type": (region.get("type") or "unknown").lower(),
            "bbox": _normalize_bbox(bbox, width, height),
            "label": region.get("label") or "",
            "confidence": float(region.get("confidence") or 0.0),
        }
        detail_number = region.get("detail_number")
        if detail_number is not None:
            normalized["detail_number"] = str(detail_number)
        normalized_regions.append(normalized)

    sheet_reflection = result.get("sheet_reflection") if isinstance(result, dict) else None
    page_type = result.get("page_type") if isinstance(result, dict) else None
    cross_refs = result.get("cross_references") if isinstance(result, dict) else None

    if not isinstance(sheet_reflection, str):
        sheet_reflection = ""
    if not isinstance(page_type, str):
        page_type = "unknown"
    if not isinstance(cross_refs, list):
        cross_refs = []
    cross_refs = [str(r) for r in cross_refs if r]

    logger.info(
        "[Brain Mode] %s: %s regions, %s cross refs",
        page_name,
        len(normalized_regions),
        len(cross_refs),
    )

    return {
        "regions": normalized_regions,
        "sheet_reflection": sheet_reflection,
        "page_type": page_type,
        "cross_references": cross_refs,
    }
