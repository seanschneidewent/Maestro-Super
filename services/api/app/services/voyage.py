"""Voyage AI embedding service for pointer semantic search."""

import logging

import voyageai

from app.config import get_settings
from app.utils.retry import with_retry

logger = logging.getLogger(__name__)


def _get_voyage_client() -> voyageai.Client:
    """Get Voyage AI client instance."""
    settings = get_settings()
    if not settings.voyage_api_key:
        raise ValueError("VOYAGE_API_KEY not configured")
    return voyageai.Client(api_key=settings.voyage_api_key)


async def _embed_text_impl(text: str) -> list[float]:
    """Internal implementation of text embedding."""
    client = _get_voyage_client()
    response = client.embed([text], model="voyage-3")
    return response.embeddings[0]


async def embed_text(text: str) -> list[float]:
    """Generate 1024-dim embedding using voyage-3 with retry.

    Args:
        text: Text to embed

    Returns:
        1024-dimension embedding vector
    """
    return await with_retry(
        _embed_text_impl,
        text,
        max_attempts=3,
        base_delay=1.0,
        exceptions=(Exception,),
    )


async def embed_pointer(
    title: str,
    description: str,
    text_spans: list[str] | None,
) -> list[float]:
    """Construct embedding text from pointer fields and embed.

    Combines title, description, and text_spans into a single
    text block for embedding.

    Args:
        title: Pointer title
        description: Pointer description
        text_spans: Extracted text elements

    Returns:
        1024-dimension embedding vector
    """
    spans_text = " ".join(text_spans) if text_spans else ""
    embedding_text = f"{title} {description} {spans_text}"
    return await embed_text(embedding_text)
