import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, user='postgres', password='maestro', dbname='maestro')
cur = conn.cursor()

# Reassign the big project (c33f5053's) to Sean's dev user
sean_uid = '081745ac-5892-4e79-aed9-1624ff4ad722'
big_project = '2ce9eb03-9693-4355-917d-533501cbb15c'

cur.execute("UPDATE projects SET user_id = %s WHERE id = %s", (sean_uid, big_project))
print(f"Updated project owner: {cur.rowcount} rows")

# Check completed pages
cur.execute("""
    SELECT COUNT(*), 
           SUM(CASE WHEN processing_status = 'completed' THEN 1 ELSE 0 END) as completed,
           SUM(CASE WHEN regions IS NOT NULL THEN 1 ELSE 0 END) as has_regions
    FROM pages p JOIN disciplines d ON p.discipline_id = d.id 
    WHERE d.project_id = %s
""", (big_project,))
row = cur.fetchone()
print(f"Big project: {row[0]} pages, {row[1]} completed, {row[2]} with regions")

# Get project name
cur.execute("SELECT name FROM projects WHERE id = %s", (big_project,))
print(f"Project name: {cur.fetchone()[0]}")

conn.commit()
conn.close()
print("Done!")
