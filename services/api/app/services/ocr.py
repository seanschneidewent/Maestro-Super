"""
OCR service using Tesseract for text extraction.
"""

import io
import logging

import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)


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
        # Return empty list on failure
        return []
