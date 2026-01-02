-- Hybrid search function combining keyword and vector search
-- Run this in Supabase SQL Editor

CREATE OR REPLACE FUNCTION hybrid_search(
  query_text TEXT,
  query_embedding vector(1024),
  p_project_id UUID,
  discipline_filter TEXT DEFAULT NULL,
  match_count INT DEFAULT 10
)
RETURNS TABLE (
  pointer_id UUID,
  title TEXT,
  page_id UUID,
  page_name TEXT,
  discipline TEXT,
  relevance_snippet TEXT,
  score FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  WITH
  -- Keyword search using ts_rank
  keyword_search AS (
    SELECT
      ptr.id,
      ts_rank_cd(
        to_tsvector('english',
          COALESCE(ptr.title, '') || ' ' ||
          COALESCE(ptr.description, '') || ' ' ||
          COALESCE(array_to_string(ptr.text_spans, ' '), '')
        ),
        plainto_tsquery('english', query_text)
      ) AS keyword_rank
    FROM pointers ptr
    JOIN pages pg ON ptr.page_id = pg.id
    JOIN disciplines d ON pg.discipline_id = d.id
    WHERE d.project_id = p_project_id
      AND (discipline_filter IS NULL OR d.name = discipline_filter)
      AND to_tsvector('english',
            COALESCE(ptr.title, '') || ' ' ||
            COALESCE(ptr.description, '') || ' ' ||
            COALESCE(array_to_string(ptr.text_spans, ' '), '')
          ) @@ plainto_tsquery('english', query_text)
  ),

  -- Vector search using cosine similarity
  vector_search AS (
    SELECT
      ptr.id,
      1 - (ptr.embedding <=> query_embedding) AS vector_score
    FROM pointers ptr
    JOIN pages pg ON ptr.page_id = pg.id
    JOIN disciplines d ON pg.discipline_id = d.id
    WHERE d.project_id = p_project_id
      AND (discipline_filter IS NULL OR d.name = discipline_filter)
      AND ptr.embedding IS NOT NULL
    ORDER BY ptr.embedding <=> query_embedding
    LIMIT match_count * 2  -- Get extra for merging
  ),

  -- Normalize keyword ranks to 0-1 range
  keyword_normalized AS (
    SELECT
      id,
      keyword_rank,
      keyword_rank / NULLIF(MAX(keyword_rank) OVER (), 0) AS norm_rank
    FROM keyword_search
  ),

  -- Combine results with full outer join
  combined AS (
    SELECT
      COALESCE(k.id, v.id) AS id,
      COALESCE(k.keyword_rank, 0) AS keyword_rank,
      COALESCE(v.vector_score, 0) AS vector_score,
      -- Weighted combination: 0.3 keyword (normalized) + 0.7 vector
      (COALESCE(k.norm_rank, 0) * 0.3 + COALESCE(v.vector_score, 0) * 0.7) AS combined_score
    FROM keyword_normalized k
    FULL OUTER JOIN vector_search v ON k.id = v.id
  )

  SELECT
    c.id AS pointer_id,
    ptr.title,
    pg.id AS page_id,
    pg.page_name,
    d.display_name AS discipline,
    LEFT(ptr.description, 200) AS relevance_snippet,
    c.combined_score AS score
  FROM combined c
  JOIN pointers ptr ON c.id = ptr.id
  JOIN pages pg ON ptr.page_id = pg.id
  JOIN disciplines d ON pg.discipline_id = d.id
  ORDER BY c.combined_score DESC
  LIMIT match_count;
END;
$$;
