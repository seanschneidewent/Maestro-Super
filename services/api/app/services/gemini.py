"""
Gemini AI service for context extraction.
"""

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


async def analyze_pointer(image_base64: str, context: str) -> dict:
    """
    Analyze a context pointer image using Gemini.

    Args:
        image_base64: Base64 encoded image of the pointer region
        context: Surrounding context text for better analysis

    Returns:
        Dictionary with AI analysis results:
        - technical_description: str
        - trade_category: str
        - elements: list[dict]
        - measurements: list[dict]
        - recommendations: str
        - issues: list[dict]
    """
    raise NotImplementedError("Gemini pointer analysis not yet implemented")


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
