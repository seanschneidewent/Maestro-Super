"""Hybrid search service combining keyword and vector search."""

import logging
import math

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.page import Page
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


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    length = min(len(vec_a), len(vec_b))
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for i in range(length):
        a = float(vec_a[i])
        b = float(vec_b[i])
        dot += a * b
        norm_a += a * a
        norm_b += b * b
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


async def embed_page_reflection(sheet_reflection: str) -> list[float] | None:
    if not sheet_reflection:
        return None
    return await embed_text(sheet_reflection)


async def embed_regions(regions: list[dict] | None) -> list[dict]:
    if not regions:
        return []

    embedded_regions: list[dict] = []
    for region in regions:
        if not isinstance(region, dict):
            continue
        label = str(region.get("label") or "")
        region_type = str(region.get("type") or "")
        detail_number = region.get("detail_number")
        text = f"{region_type}: {label}".strip()
        if detail_number:
            text = f"{text} (Detail {detail_number})"
        if not text.strip():
            embedded_regions.append(region)
            continue
        try:
            region["embedding"] = await embed_text(text)
        except Exception as e:
            logger.warning(f"Region embedding failed for {label or region_type}: {e}")
        embedded_regions.append(region)

    return embedded_regions


async def vector_search_pages(
    db: Session,
    query_embedding: list[float],
    project_id: str,
    limit: int = 5,
) -> list[Page]:
    if not query_embedding:
        return []

    if not hasattr(Page, "page_embedding"):
        logger.warning("Page embedding column not available; vector search skipped")
        return []

    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    result = db.execute(
        text("""
            SELECT pages.id
            FROM pages
            JOIN disciplines ON pages.discipline_id = disciplines.id
            WHERE disciplines.project_id = CAST(:project_id AS uuid)
              AND pages.page_embedding IS NOT NULL
            ORDER BY pages.page_embedding <=> CAST(:query_embedding AS vector)
            LIMIT :limit
        """),
        {
            "project_id": project_id,
            "query_embedding": embedding_str,
            "limit": limit,
        },
    )

    page_ids = [str(row[0]) for row in result.fetchall()]
    if not page_ids:
        return []

    pages = (
        db.query(Page)
        .filter(Page.id.in_(page_ids))
        .all()
    )
    page_map = {str(p.id): p for p in pages}
    return [page_map[pid] for pid in page_ids if pid in page_map]


async def search_pages_and_regions(
    db: Session,
    query: str,
    project_id: str,
    limit: int = 5,
    similarity_threshold: float = 0.7,
) -> dict[str, list[dict]]:
    """
    Two-level search:
    1. Find relevant pages via sheet_reflection embedding
    2. Find relevant regions within those pages

    Returns: {page_id: [region1, region2, ...]}
    """
    query_embedding = await embed_text(query)

    pages = await vector_search_pages(
        db,
        query_embedding=query_embedding,
        project_id=project_id,
        limit=limit,
    )

    results: dict[str, list[dict]] = {}
    for page in pages:
        matching_regions: list[dict] = []
        for region in page.regions or []:
            if not isinstance(region, dict):
                continue
            embedding = region.get("embedding")
            similarity = _cosine_similarity(query_embedding, embedding) if embedding else 0.0

            if similarity <= 0.0:
                # Fallback: keyword match on label/type
                haystack = f"{region.get('type', '')} {region.get('label', '')} {region.get('detail_number', '')}".lower()
                tokens = [t for t in query.lower().split() if t]
                if tokens and any(t in haystack for t in tokens):
                    similarity = 0.5

            if similarity >= similarity_threshold:
                region_copy = dict(region)
                region_copy.pop("embedding", None)
                region_copy["_similarity"] = similarity
                matching_regions.append(region_copy)

        if matching_regions:
            matching_regions.sort(key=lambda r: r.get("_similarity", 0.0), reverse=True)
            results[str(page.id)] = matching_regions

    return results
