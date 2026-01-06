"""
OCR service using pdf2image (Poppler) + Tesseract hybrid extraction.
"""

import io
import logging

import pytesseract
from PIL import Image

from app.services.pdf_renderer import crop_pdf_region

logger = logging.getLogger(__name__)


# Re-export crop_pdf_region from pdf_renderer for backwards compatibility
__all__ = ["crop_pdf_region", "extract_text_with_positions", "extract_full_page_text"]


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


async def extract_full_page_text(
    image_bytes: bytes,
    max_retries: int = 3,
) -> tuple[str, list[dict]]:
    """
    Run Tesseract on full page PNG with retry logic.

    Args:
        image_bytes: PNG image bytes of the page
        max_retries: Maximum retry attempts on failure (default 3)

    Returns:
        (full_text, ocr_spans) where ocr_spans is [{text, x, y, w, h, confidence}]
        Returns ("", []) if all retries fail.
    """
    import asyncio

    for attempt in range(max_retries):
        try:
            # Use existing extract_text_with_positions function
            spans = extract_text_with_positions(image_bytes)

            # Join all span text for full_text
            full_text = " ".join(span["text"] for span in spans)

            logger.info(f"Full page OCR complete: {len(spans)} spans, {len(full_text)} chars")
            return full_text, spans

        except Exception as e:
            logger.warning(f"OCR attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(1.0)  # 1s backoff between retries

    logger.error(f"Full page OCR failed after {max_retries} attempts")
    return "", []
