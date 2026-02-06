import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, user='postgres', password='maestro', dbname='maestro')
cur = conn.cursor()

cur.execute("SELECT data_type, udt_name FROM information_schema.columns WHERE table_name='pages' AND column_name='page_embedding'")
row = cur.fetchone()
print(f"page_embedding type: {row}")

cur.execute("SELECT COUNT(*) FROM pages WHERE page_embedding IS NOT NULL")
print(f"Pages with embeddings: {cur.fetchone()[0]}")

conn.close()
