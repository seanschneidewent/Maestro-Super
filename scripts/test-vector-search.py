"""Test vector search directly to find the real error."""
import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, user='postgres', password='maestro', dbname='maestro')
cur = conn.cursor()

# Check pgvector
cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'")
print(f"pgvector: {cur.fetchone()}")

# Check embedding dimensions
cur.execute("SELECT id, octet_length(page_embedding::text) FROM pages WHERE page_embedding IS NOT NULL LIMIT 1")
row = cur.fetchone()
if row:
    print(f"Sample embedding exists: page {row[0]}, text length {row[1]}")
else:
    print("NO EMBEDDINGS FOUND")

# Try the actual vector search query
try:
    cur.execute("""
        SELECT pages.id FROM pages 
        JOIN disciplines ON pages.discipline_id = disciplines.id 
        WHERE disciplines.project_id = CAST(%s AS uuid) 
        AND pages.page_embedding IS NOT NULL 
        ORDER BY pages.page_embedding <=> CAST(%s AS vector) 
        LIMIT 5
    """, ('2ce9eb03-9693-4355-917d-533501cbb15c', '[' + ','.join(['0.1'] * 1024) + ']'))
    results = cur.fetchall()
    print(f"Vector search works! Got {len(results)} results")
except Exception as e:
    print(f"Vector search FAILED: {e}")
    conn.rollback()

conn.close()
