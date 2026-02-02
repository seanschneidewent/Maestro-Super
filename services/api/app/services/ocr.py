"""Backwards compatibility stub for deprecated OCR module."""
from app.services.providers.ocr import *  # noqa: F401, F403
from app.services.providers.ocr import (
    crop_pdf_region,
    extract_full_page_text,
    extract_text_with_positions,
)
