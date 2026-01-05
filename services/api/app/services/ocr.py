"""
OCR service using PyMuPDF + Tesseract hybrid extraction.
"""

import io
import logging

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)


def crop_pdf_region(
    pdf_bytes: bytes,
    page_index: int,
    x_norm: float,
    y_norm: float,
    w_norm: float,
    h_norm: float,
    dpi: int = 300,
) -> bytes:
    """
    Crop a region from a PDF page to PNG.

    Normalized coords (0-1) are converted to pixels based on page dimensions.

    Args:
        pdf_bytes: Raw PDF file bytes
        page_index: Zero-based page index
        x_norm, y_norm: Top-left corner (normalized 0-1)
        w_norm, h_norm: Width and height (normalized 0-1)
        dpi: Target DPI for rendering (default 300 for retina displays)

    Returns:
        PNG image bytes of the cropped region
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    if page_index >= len(doc):
        doc.close()
        raise ValueError(f"Page index {page_index} out of range (0-{len(doc) - 1})")

    page = doc[page_index]
    page_rect = page.rect

    # Define clip rectangle in PDF coordinates (72 DPI base)
    clip_rect = fitz.Rect(
        x_norm * page_rect.width,
        y_norm * page_rect.height,
        (x_norm + w_norm) * page_rect.width,
        (y_norm + h_norm) * page_rect.height,
    )

    # Scale factor for target DPI
    scale = dpi / 72
    mat = fitz.Matrix(scale, scale)

    # Render the clipped region
    pix = page.get_pixmap(matrix=mat, clip=clip_rect)
    png_bytes = pix.tobytes("png")

    doc.close()
    logger.info(
        f"Cropped region ({x_norm:.3f}, {y_norm:.3f}, {w_norm:.3f}, {h_norm:.3f}) "
        f"at {dpi} DPI, output size: {pix.width}x{pix.height}"
    )

    return png_bytes


def extract_text_with_positions(image_bytes: bytes) -> list[dict]:
    """
    Run Tesseract OCR and return text spans with positions.

    Returns list of word-level OCR results:
    {
        "text": "word",
        "x": float (0-1 normalized),
        "y": float (0-1 normalized),
        "w": float (0-1 normalized),
        "h": float (0-1 normalized),
        "confidence": int (0-100)
    }

    Coordinates are normalized to 0-1 relative to the input image dimensions.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        width, height = image.size

        # Get word-level bounding boxes from Tesseract
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

        spans = []
        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            conf = int(data["conf"][i])

            # Skip empty text or low confidence results
            if not text or conf < 30:
                continue

            # Normalize coordinates to 0-1
            spans.append(
                {
                    "text": text,
                    "x": data["left"][i] / width,
                    "y": data["top"][i] / height,
                    "w": data["width"][i] / width,
                    "h": data["height"][i] / height,
                    "confidence": conf,
                }
            )

        logger.info(f"OCR extracted {len(spans)} text spans from image")
        return spans

    except Exception as e:
        logger.error(f"OCR extraction failed: {e}")
        # Return empty list on failure - Gemini can still analyze the image
        return []


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
    raise NotImplementedError("Hybrid OCR not yet implemented - use extract_text_with_positions instead")


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
    raise NotImplementedError("Full page OCR not yet implemented")


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
    raise NotImplementedError("Use crop_pdf_region with pdf_bytes instead")
