"""Hybrid search service combining keyword and vector search."""

import logging

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.services.voyage import embed_text

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
    # Generate query embedding using Voyage
    embedding = await embed_text(query)

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
            "query_text": query,
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
