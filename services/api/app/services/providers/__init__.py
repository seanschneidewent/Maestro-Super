"""External API provider wrappers."""

from app.services.providers.claude import generate_response, stream_response
from app.services.providers.gemini import (
    analyze_page_pass_1,
    analyze_pointer,
    run_agent_query as gemini_run_agent_query,
)
from app.services.providers.ocr import (
    crop_pdf_region,
    extract_full_page_text,
    extract_text_with_positions,
)
from app.services.providers.pdf_renderer import (
    crop_pdf_region as pdf_crop_region,
    get_pdf_page_count,
    pdf_page_to_image,
)
from app.services.providers.voyage import embed_pointer, embed_text

__all__ = [
    # claude
    "generate_response",
    "stream_response",
    # gemini
    "analyze_page_pass_1",
    "analyze_pointer",
    "gemini_run_agent_query",
    # ocr
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
