import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, user='postgres', password='maestro', dbname='maestro')
cur = conn.cursor()

# Check column types
for table, col in [('disciplines', 'project_id'), ('pages', 'discipline_id'), ('projects', 'id'), ('disciplines', 'id')]:
    cur.execute("SELECT data_type, udt_name FROM information_schema.columns WHERE table_name=%s AND column_name=%s", (table, col))
    row = cur.fetchone()
    print(f"{table}.{col}: {row}")

# Fix: alter disciplines.project_id from varchar to uuid  
print("\nFixing column types...")
try:
    cur.execute("ALTER TABLE disciplines ALTER COLUMN project_id TYPE uuid USING project_id::uuid")
    conn.commit()
    print("disciplines.project_id -> uuid: OK")
except Exception as e:
    print(f"Error: {e}")
    conn.rollback()

# Test search again
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
    print(f"\nVector search works! Got {len(results)} results")
except Exception as e:
    print(f"\nVector search still failing: {e}")
    conn.rollback()

conn.close()
