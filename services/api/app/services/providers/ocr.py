"""
DEPRECATED: Legacy OCR helpers.

Brain Mode now uses Agentic Vision via:
  - app.services.core.brain_mode_processor.process_page_brain_mode()
  - app.services.providers.gemini.analyze_sheet_brain_mode()

Use app.services.providers.pdf_renderer.crop_pdf_region() for PDF cropping.
This module remains for legacy compatibility and will be removed in a future release.
"""

import io
import logging
import warnings
from typing import Optional

from PIL import Image

from app.services.providers.pdf_renderer import crop_pdf_region

logger = logging.getLogger(__name__)

warnings.warn(
    "app.services.providers.ocr is deprecated. "
    "Use app.services.providers.pdf_renderer and Agentic Vision pipeline helpers instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Optional EasyOCR dependency (legacy pipeline)
try:
    import easyocr  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    easyocr = None
    np = None

# Global EasyOCR reader - loaded lazily on first use
_easyocr_reader: Optional[object] = None


def get_easyocr_reader() -> Optional[object]:
    """Get or create the global EasyOCR reader (lazy loading)."""
    if easyocr is None:
        logger.warning("[OCR] EasyOCR not installed - OCR disabled")
        return None
    global _easyocr_reader
    if _easyocr_reader is None:
        logger.info("[OCR] Loading EasyOCR model (first use)...")
        _easyocr_reader = easyocr.Reader(['en'], gpu=False)
        logger.info("[OCR] EasyOCR model loaded")
    return _easyocr_reader


# Re-export crop_pdf_region from pdf_renderer for backwards compatibility
__all__ = ["crop_pdf_region", "extract_text_with_positions", "extract_full_page_text"]


def extract_text_with_positions(image_bytes: bytes) -> list[dict]:
    """
    Run EasyOCR and return text spans with positions.

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
        if easyocr is None or np is None:
            logger.warning("[OCR] EasyOCR not installed - returning empty spans")
            return []

        image = Image.open(io.BytesIO(image_bytes))
        width, height = image.size
        image_array = np.array(image)

        # Get bounding boxes from EasyOCR
        reader = get_easyocr_reader()
        if reader is None:
            return []
        results = reader.readtext(image_array)

        spans = []
        for bbox_points, text, confidence in results:
            text = text.strip()
            conf = int(confidence * 100)

            # Skip empty text or low confidence results
            if not text or conf < 30:
                continue

            # Convert 4-point bbox to x, y, w, h
            xs = [p[0] for p in bbox_points]
            ys = [p[1] for p in bbox_points]
            x0 = min(xs)
            y0 = min(ys)
            x1 = max(xs)
            y1 = max(ys)

            # Normalize coordinates to 0-1
            spans.append(
                {
                    "text": text,
                    "x": x0 / width,
                    "y": y0 / height,
                    "w": (x1 - x0) / width,
                    "h": (y1 - y0) / height,
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
