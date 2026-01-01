"""
Claude AI service for page analysis and query responses.
"""

import logging
from collections.abc import AsyncIterator

import anthropic

from app.config import get_settings

logger = logging.getLogger(__name__)


def _get_claude_client() -> anthropic.Anthropic:
    """Get Claude API client."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ValueError("Anthropic API key must be configured")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


async def analyze_page_pass_1(image_base64: str) -> str:
    """
    Analyze a construction drawing page and return initial context summary.

    This is Pass 1 processing - generates a brief 2-3 sentence description
    of the page type, key elements, and notable features.

    Args:
        image_base64: Base64-encoded PNG image of the page

    Returns:
        Initial context summary (2-3 sentences)
    """
    try:
        client = _get_claude_client()

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Describe this construction drawing page briefly. "
                                "Include: what type of page it is (floor plan, detail sheet, "
                                "elevation, section, schedule, notes, etc.), key elements visible "
                                "(keynotes, legends, details, general notes, dimensions, etc.), "
                                "and any notable features. Keep it to 2-3 sentences."
                            ),
                        },
                    ],
                }
            ],
        )

        result = message.content[0].text
        logger.info(
            f"Pass 1 analysis complete. Tokens: {message.usage.input_tokens} in, "
            f"{message.usage.output_tokens} out"
        )
        return result

    except Exception as e:
        logger.error(f"Claude Pass 1 analysis failed: {e}")
        raise


async def generate_response(
    query_text: str,
    context_pointers: list[dict],
    page_contexts: list[dict],
    discipline_contexts: list[dict],
) -> dict:
    """
    Generate AI response to user query using Claude.

    Args:
        query_text: User's question
        context_pointers: Relevant context pointers with AI analysis
        page_contexts: Relevant page contexts
        discipline_contexts: Relevant discipline contexts

    Returns:
        Dictionary with:
        - response_text: str
        - referenced_pointers: list[dict]
        - tokens_used: int
    """
    raise NotImplementedError("Claude query response not yet implemented")


async def stream_response(
    query_text: str,
    context_pointers: list[dict],
    page_contexts: list[dict],
    discipline_contexts: list[dict],
) -> AsyncIterator[str]:
    """
    Stream AI response to user query using Claude.

    Args:
        query_text: User's question
        context_pointers: Relevant context pointers with AI analysis
        page_contexts: Relevant page contexts
        discipline_contexts: Relevant discipline contexts

    Yields:
        Response text chunks
    """
    raise NotImplementedError("Claude streaming response not yet implemented")
    yield ""  # noqa: unreachable
