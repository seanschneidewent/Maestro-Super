"""
OCR service using PyMuPDF + Tesseract hybrid extraction.

TODO: Implement in AI integration phase.
"""


async def extract_text_from_region(
    pdf_path: str,
    page_number: int,
    x_norm: float,
    y_norm: float,
    w_norm: float,
    h_norm: float,
) -> dict:
    """
    Extract text from a region of a PDF page using hybrid OCR.

    Uses PyMuPDF native text extraction first, falls back to
    Tesseract OCR if native extraction fails or is incomplete.

    Args:
        pdf_path: Path to PDF file (Supabase Storage path)
        page_number: Page number (1-indexed)
        x_norm, y_norm, w_norm, h_norm: Normalized bounds (0-1)

    Returns:
        Dictionary with:
        - native_text: str (from PyMuPDF)
        - ocr_text: str | None (from Tesseract if needed)
        - combined_text: str (deduplicated merge)
        - confidence: float (0-1)
    """
    raise NotImplementedError("OCR integration not yet implemented")


async def extract_page_text(pdf_path: str, page_number: int) -> dict:
    """
    Extract all text from a PDF page.

    Args:
        pdf_path: Path to PDF file (Supabase Storage path)
        page_number: Page number (1-indexed)

    Returns:
        Dictionary with:
        - text_blocks: list[dict] with position and content
        - full_text: str
    """
    raise NotImplementedError("OCR integration not yet implemented")


async def capture_region_snapshot(
    pdf_path: str,
    page_number: int,
    x_norm: float,
    y_norm: float,
    w_norm: float,
    h_norm: float,
    dpi: int = 150,
) -> bytes:
    """
    Capture a high-DPI snapshot of a PDF region.

    Args:
        pdf_path: Path to PDF file (Supabase Storage path)
        page_number: Page number (1-indexed)
        x_norm, y_norm, w_norm, h_norm: Normalized bounds (0-1)
        dpi: Target DPI for capture (default 150)

    Returns:
        PNG image bytes
    """
    raise NotImplementedError("OCR integration not yet implemented")
