"""
PDF processing utilities for page rendering.
"""

import logging

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def pdf_page_to_image(
    pdf_bytes: bytes,
    page_index: int = 0,
    dpi: int = 150,
) -> bytes:
    """
    Convert a PDF page to a PNG image.

    Args:
        pdf_bytes: PDF file as bytes
        page_index: Zero-based page index (default: 0)
        dpi: Resolution for rendering (default: 150 DPI for good quality/size balance)

    Returns:
        PNG image as bytes
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        if page_index >= len(doc):
            raise ValueError(f"Page index {page_index} out of range (0-{len(doc) - 1})")

        page = doc[page_index]

        # Scale factor: PDF default is 72 DPI, we want 150 DPI
        scale = dpi / 72
        mat = fitz.Matrix(scale, scale)

        # Render page to pixmap
        pix = page.get_pixmap(matrix=mat)

        # Convert to PNG bytes
        png_bytes = pix.tobytes("png")

        doc.close()

        logger.debug(
            f"Converted PDF page {page_index} to PNG: {len(png_bytes)} bytes at {dpi} DPI"
        )

        return png_bytes

    except Exception as e:
        logger.error(f"Failed to convert PDF page {page_index} to image: {e}")
        raise


def get_pdf_page_count(pdf_bytes: bytes) -> int:
    """
    Get the number of pages in a PDF.

    Args:
        pdf_bytes: PDF file as bytes

    Returns:
        Number of pages
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        count = len(doc)
        doc.close()
        return count
    except Exception as e:
        logger.error(f"Failed to get PDF page count: {e}")
        raise
