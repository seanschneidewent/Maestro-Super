"""
Brain Mode Processor - single-pass sheet comprehension.

Generates page structure regions and a superintendent-style reflection
to power query-time precision.
"""

from __future__ import annotations

import logging

from app.services.providers.gemini import analyze_sheet_brain_mode
from app.utils.retry import with_retry

logger = logging.getLogger(__name__)


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
            "sheet_info": {...},
            "index": {...},
            "questions_this_sheet_answers": [...],
            "processing_time_ms": 12345,
        }
    """
    if not image_bytes:
        raise ValueError("image_bytes is required for Brain Mode processing")

    result, timing_ms = await with_retry(
        analyze_sheet_brain_mode,
        image_bytes=image_bytes,
        page_name=page_name,
        discipline=discipline_name,
        max_attempts=3,
        base_delay=1.0,
        exceptions=(Exception,),
    )
    if not isinstance(result, dict):
        result = {}

    regions = result.get("regions")
    if not isinstance(regions, list):
        regions = []

    cross_refs = result.get("cross_references")
    if not isinstance(cross_refs, list):
        cross_refs = []
    cross_refs = [str(ref) for ref in cross_refs if ref]

    sheet_reflection = result.get("sheet_reflection")
    if not isinstance(sheet_reflection, str):
        sheet_reflection = ""

    page_type = result.get("page_type")
    if not isinstance(page_type, str):
        page_type = "unknown"

    sheet_info = result.get("sheet_info")
    if not isinstance(sheet_info, dict):
        sheet_info = {}

    index = result.get("index")
    if not isinstance(index, dict):
        index = {}

    questions = result.get("questions_this_sheet_answers")
    if not isinstance(questions, list):
        questions = []
    questions = [str(question) for question in questions if question]

    logger.info(
        "[Brain Mode] %s: %s regions, %s cross refs in %sms",
        page_name,
        len(regions),
        len(cross_refs),
        timing_ms,
    )

    return {
        "regions": regions,
        "sheet_reflection": sheet_reflection,
        "page_type": page_type,
        "cross_references": cross_refs,
        "sheet_info": sheet_info,
        "index": index,
        "questions_this_sheet_answers": questions,
        "processing_time_ms": timing_ms,
    }
