import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, user='postgres', password='maestro', dbname='maestro')
cur = conn.cursor()

# Count pages for Sean's project
cur.execute("""
    SELECT d.project_id, COUNT(p.id) 
    FROM pages p JOIN disciplines d ON p.discipline_id = d.id 
    WHERE d.project_id = '7600d59e-a1dc-44b4-a1d8-453d7c2f409d' 
    GROUP BY d.project_id
""")
for row in cur.fetchall():
    print(f"Project {row[0][:8]}...: {row[1]} pages")

# Check page_image_path and page_image_ready
cur.execute("""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN page_image_path IS NOT NULL AND page_image_path != '' THEN 1 ELSE 0 END) as has_image,
        SUM(CASE WHEN page_image_ready = true THEN 1 ELSE 0 END) as image_ready,
        SUM(CASE WHEN processing_status = 'completed' THEN 1 ELSE 0 END) as completed,
        SUM(CASE WHEN regions IS NOT NULL THEN 1 ELSE 0 END) as has_regions,
        SUM(CASE WHEN sheet_reflection IS NOT NULL AND sheet_reflection != '' THEN 1 ELSE 0 END) as has_reflection
    FROM pages p JOIN disciplines d ON p.discipline_id = d.id 
    WHERE d.project_id = '7600d59e-a1dc-44b4-a1d8-453d7c2f409d'
""")
row = cur.fetchone()
print(f"Total: {row[0]}, has_image: {row[1]}, image_ready: {row[2]}, completed: {row[3]}, has_regions: {row[4]}, has_reflection: {row[5]}")

# Check what the /projects/{id}/full endpoint returns
cur.execute("""
    SELECT p.id, p.page_name, p.processing_status, p.page_image_ready,
           LEFT(p.page_image_path, 50) as img_path
    FROM pages p JOIN disciplines d ON p.discipline_id = d.id 
    WHERE d.project_id = '7600d59e-a1dc-44b4-a1d8-453d7c2f409d'
    LIMIT 5
""")
print("\nSample pages:")
for row in cur.fetchall():
    print(f"  {row[1]} | status={row[2]} | img_ready={row[3]} | path={row[4]}")

conn.close()
