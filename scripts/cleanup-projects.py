import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, user='postgres', password='maestro', dbname='maestro')
cur = conn.cursor()

big_project = '2ce9eb03-9693-4355-917d-533501cbb15c'

# Delete projects that aren't the big one (and their orphan data)
cur.execute("SELECT id, name FROM projects WHERE id != %s", (big_project,))
others = cur.fetchall()
for pid, name in others:
    print(f"Removing: {name} ({pid})")
    cur.execute("DELETE FROM queries WHERE conversation_id IN (SELECT id FROM conversations WHERE project_id = %s)", (pid,))
    cur.execute("DELETE FROM conversations WHERE project_id = %s", (pid,))
    cur.execute("DELETE FROM pointers WHERE page_id IN (SELECT p.id FROM pages p JOIN disciplines d ON p.discipline_id = d.id WHERE d.project_id = %s)", (pid,))
    cur.execute("DELETE FROM pages WHERE discipline_id IN (SELECT id FROM disciplines WHERE project_id = %s)", (pid,))
    cur.execute("DELETE FROM disciplines WHERE project_id = %s", (pid,))
    cur.execute("DELETE FROM projects WHERE id = %s", (pid,))

conn.commit()

# Verify
cur.execute("SELECT id, name FROM projects")
for row in cur.fetchall():
    print(f"Remaining: {row[1]} ({row[0]})")

cur.execute("""
    SELECT COUNT(*) FROM pages p 
    JOIN disciplines d ON p.discipline_id = d.id 
    WHERE d.project_id = %s
""", (big_project,))
print(f"Pages: {cur.fetchone()[0]}")

conn.close()
print("Done!")
