"""Hybrid search service combining keyword and vector search."""

import logging

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.services.providers.voyage import embed_text

logger = logging.getLogger(__name__)


async def search_pointers(
    db: Session,
    query: str,
    project_id: str,
    discipline: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """
    Hybrid search combining keyword and vector search.

    Args:
        db: Database session
        query: Search query text
        project_id: Project UUID
        discipline: Optional discipline filter (e.g., "architectural")
        limit: Max results (default 10)

    Returns:
        List of search results with pointer_id, title, page_id, etc.
    """
    # Strip common stop words that don't add search value
    STOP_WORDS = {"a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must", "shall", "can", "need", "dare", "ought", "used", "it", "its", "this", "that", "these", "those", "i", "you", "he", "she", "we", "they", "what", "which", "who", "whom", "where", "when", "why", "how", "all", "each", "every", "both", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just", "also"}

    words = [w for w in query.lower().split() if w not in STOP_WORDS]
    clean_query = " ".join(words) if words else query

    # Generate query embedding using Voyage
    embedding = await embed_text(clean_query)

    # Format embedding as PostgreSQL array literal
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    # Call the PostgreSQL hybrid_search function
    # Use CAST() instead of :: to avoid SQLAlchemy parameter binding conflicts
    result = db.execute(
        text("""
            SELECT * FROM hybrid_search(
                :query_text,
                CAST(:query_embedding AS vector),
                CAST(:project_id AS uuid),
                :discipline_filter,
                :match_count
            )
        """),
        {
            "query_text": clean_query,
            "query_embedding": embedding_str,
            "project_id": project_id,
            "discipline_filter": discipline,
            "match_count": limit,
        }
    )

    # Convert to list of dicts
    columns = [
        "pointer_id",
        "title",
        "page_id",
        "page_name",
        "discipline",
        "relevance_snippet",
        "score",
    ]
    rows = result.fetchall()

    return [
        {col: str(val) if col.endswith("_id") else val for col, val in zip(columns, row)}
        for row in rows
    ]
