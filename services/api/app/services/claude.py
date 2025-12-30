"""
Claude AI service for query responses.

TODO: Implement in AI integration phase.
"""

from collections.abc import AsyncIterator


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
    raise NotImplementedError("Claude integration not yet implemented")


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
    raise NotImplementedError("Claude integration not yet implemented")
    yield ""  # noqa: unreachable
