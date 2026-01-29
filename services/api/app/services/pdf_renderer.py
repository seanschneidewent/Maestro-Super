"""Backwards compatibility stub - module moved to providers/pdf_renderer.py"""
from app.services.providers.pdf_renderer import *  # noqa: F401, F403
from app.services.providers.pdf_renderer import (
    crop_pdf_region,
    get_pdf_page_count,
    pdf_page_to_image,
)
