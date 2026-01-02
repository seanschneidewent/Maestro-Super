"""
Gemini AI service for context extraction.
"""

import json
import logging

from google import genai
from google.genai import types

from app.config import get_settings

logger = logging.getLogger(__name__)


def _get_gemini_client() -> genai.Client:
    """Get Gemini client."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise ValueError("Gemini API key must be configured")
    return genai.Client(api_key=settings.gemini_api_key)


async def analyze_page_pass_1(image_bytes: bytes) -> str:
    """
    Pass 1: Analyze a construction drawing page and return initial context summary.

    Uses Gemini 2.0 Flash for fast, cost-effective image analysis.

    Args:
        image_bytes: PNG image bytes of the page

    Returns:
        Initial context summary (2-3 sentences)
    """
    try:
        client = _get_gemini_client()

        prompt = (
            "Describe this construction drawing page briefly. "
            "Include: what type of page it is (floor plan, detail sheet, "
            "elevation, section, schedule, notes, etc.), key elements visible "
            "(keynotes, legends, details, general notes, dimensions, etc.), "
            "and any notable features. Keep it to 2-3 sentences."
        )

        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[
                types.Content(
                    parts=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                        types.Part.from_text(text=prompt),
                    ]
                )
            ],
        )

        result = response.text
        logger.info("Pass 1 analysis complete with Gemini Flash")
        return result

    except Exception as e:
        logger.error(f"Gemini Pass 1 analysis failed: {e}")
        raise


async def analyze_pointer(
    image_bytes: bytes,
    ocr_spans: list[dict],
    page_context: str,
    all_page_names: list[str],
) -> dict:
    """
    Analyze a pointer region with Gemini.

    Args:
        image_bytes: Cropped region PNG bytes
        ocr_spans: OCR text with positions [{text, x, y, w, h, confidence}]
        page_context: Initial context from Pass 1
        all_page_names: List of all page names in project for reference matching

    Returns:
        Dictionary with:
        - title: short descriptive title
        - description: 1-2 paragraph description
        - references: [{target_page, justification}]
        - text_spans: list of main text elements
    """
    try:
        client = _get_gemini_client()

        # Format OCR text for prompt
        ocr_text = "\n".join([s["text"] for s in ocr_spans]) if ocr_spans else "(No text detected)"

        prompt = f"""Analyze this detail from a construction drawing.

OCR-extracted text from this region:
{ocr_text}

Context about this page (from Pass 1 analysis):
{page_context or "(No context available)"}

All pages in this project: {', '.join(all_page_names) if all_page_names else "(No pages available)"}

Tasks:
1. Generate a short, descriptive title for this detail (max 10 words)
2. Write 1-2 paragraphs describing what this detail shows and its purpose
3. Identify ALL references to other pages (e.g., "See S2.01", "Detail 3/A1.02", "Refer to Structural")
   - For each reference, provide the target page name and the text that justifies it
   - Only include references if the target page exists in the project list
4. List the main text elements as individual spans

Return JSON:
{{
  "title": "short descriptive title",
  "description": "1-2 paragraph description",
  "references": [
    {{"target_page": "page_name", "justification": "the text mentioning this reference"}}
  ],
  "text_spans": ["text1", "text2", "text3"]
}}"""

        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[
                types.Content(
                    parts=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                        types.Part.from_text(text=prompt),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )

        result = json.loads(response.text)
        logger.info(f"Pointer analysis complete: {result.get('title', 'Unknown')}")
        return result

    except Exception as e:
        logger.error(f"Gemini pointer analysis failed: {e}")
        # Return fallback response on failure
        return {
            "title": "Analysis Failed",
            "description": f"Unable to analyze this region. Error: {str(e)}",
            "references": [],
            "text_spans": [s["text"] for s in ocr_spans] if ocr_spans else [],
        }


async def analyze_page_pass2(
    image_base64: str,
    pass1_output: dict,
    cross_references: list[dict],
) -> dict:
    """
    Pass 2: Enrich page context with cross-references.

    Args:
        image_base64: Base64 encoded page image
        pass1_output: Output from pass 1 analysis
        cross_references: References to/from other pages

    Returns:
        Dictionary with pass 2 analysis results
    """
    raise NotImplementedError("Gemini Pass 2 not yet implemented")


async def analyze_discipline_pass3(
    discipline_code: str,
    page_contexts: list[dict],
) -> dict:
    """
    Pass 3: Roll up discipline context from all pages.

    Args:
        discipline_code: Discipline code (A, S, M, E, P, etc.)
        page_contexts: List of page context summaries

    Returns:
        Dictionary with discipline-level analysis
    """
    raise NotImplementedError("Gemini Pass 3 not yet implemented")
