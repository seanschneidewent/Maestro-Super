"""External API provider wrappers."""

from __future__ import annotations

from app.services.providers.claude import generate_response, stream_response
from app.services.providers.gemini import (
    analyze_page_pass_1,
    analyze_pointer,
    analyze_sheet_brain_mode,
    run_agent_query as gemini_run_agent_query,
)
from app.services.providers.pdf_renderer import (
    crop_pdf_region,
    crop_pdf_region as pdf_crop_region,
    get_pdf_page_count,
    pdf_page_to_image,
)
from app.services.providers.voyage import embed_pointer, embed_text


def extract_text_with_positions(image_bytes: bytes) -> list[dict]:
    """
    Backwards-compatible OCR helper.

    Imports the deprecated OCR module lazily so package import does not
    eagerly pull legacy dependencies or emit deprecation warnings.
    """
    from app.services.providers.ocr import (
        extract_text_with_positions as _extract_text_with_positions,
    )

    return _extract_text_with_positions(image_bytes)


async def extract_full_page_text(
    image_bytes: bytes,
    max_retries: int = 3,
) -> tuple[str, list[dict]]:
    """Backwards-compatible async OCR helper (lazy import)."""
    from app.services.providers.ocr import (
        extract_full_page_text as _extract_full_page_text,
    )

    return await _extract_full_page_text(image_bytes=image_bytes, max_retries=max_retries)


__all__ = [
    # claude
    "generate_response",
    "stream_response",
    # gemini
    "analyze_page_pass_1",
    "analyze_pointer",
    "analyze_sheet_brain_mode",
    "gemini_run_agent_query",
    # ocr (lazy wrappers)
    "crop_pdf_region",
    "extract_full_page_text",
    "extract_text_with_positions",
    # pdf_renderer
    "pdf_crop_region",
    "get_pdf_page_count",
    "pdf_page_to_image",
    # voyage
    "embed_pointer",
    "embed_text",
]
