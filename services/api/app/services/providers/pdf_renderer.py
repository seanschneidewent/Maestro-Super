"""
PDF processing utilities using pdf2image (Poppler backend).

Handles PDF-to-image conversion and cropping.
"""

import io
import logging

from pdf2image import convert_from_bytes

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
        dpi: Resolution for rendering (default: 150 DPI)

    Returns:
        PNG image as bytes
    """
    try:
        # Convert PDF to list of PIL images
        # first_page and last_page are 1-indexed
        images = convert_from_bytes(
            pdf_bytes,
            dpi=dpi,
            first_page=page_index + 1,
            last_page=page_index + 1,
            fmt="png",
        )

        if not images:
            raise ValueError(f"No page at index {page_index}")

        # Get the single page image
        image = images[0]

        # Convert to PNG bytes
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        png_bytes = buffer.getvalue()

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
        # Convert just to count pages (low DPI for speed)
        images = convert_from_bytes(pdf_bytes, dpi=10)
        return len(images)
    except Exception as e:
        logger.error(f"Failed to get PDF page count: {e}")
        raise


def crop_pdf_region(
    pdf_bytes: bytes,
    page_index: int,
    x_norm: float,
    y_norm: float,
    w_norm: float,
    h_norm: float,
    dpi: int = 150,
) -> bytes:
    """
    Crop a region from a PDF page to PNG.

    Normalized coords (0-1) are converted to pixels based on page dimensions.

    Args:
        pdf_bytes: Raw PDF file bytes
        page_index: Zero-based page index
        x_norm, y_norm: Top-left corner (normalized 0-1)
        w_norm, h_norm: Width and height (normalized 0-1)
        dpi: Target DPI for rendering (default 150 for faster processing)

    Returns:
        PNG image bytes of the cropped region
    """
    try:
        # Render the full page at target DPI
        images = convert_from_bytes(
            pdf_bytes,
            dpi=dpi,
            first_page=page_index + 1,
            last_page=page_index + 1,
        )

        if not images:
            raise ValueError(f"No page at index {page_index}")

        image = images[0]
        width, height = image.size

        # Calculate crop box in pixels
        left = int(x_norm * width)
        top = int(y_norm * height)
        right = int((x_norm + w_norm) * width)
        bottom = int((y_norm + h_norm) * height)

        # Crop the region
        cropped = image.crop((left, top, right, bottom))

        # Convert to PNG bytes
        buffer = io.BytesIO()
        cropped.save(buffer, format="PNG")
        png_bytes = buffer.getvalue()

        logger.info(
            f"Cropped region ({x_norm:.3f}, {y_norm:.3f}, {w_norm:.3f}, {h_norm:.3f}) "
            f"at {dpi} DPI, output size: {cropped.width}x{cropped.height}"
        )

        return png_bytes

    except Exception as e:
        logger.error(f"Failed to crop PDF region: {e}")
        raise
