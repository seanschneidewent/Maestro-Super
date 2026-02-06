"""Pull page_embedding from Supabase and insert into local Postgres."""
import os
import requests
import psycopg2

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ybyqobdyvbmsiehdmxwp.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
if not SUPABASE_KEY:
    raise ValueError("SUPABASE_SERVICE_KEY environment variable required")
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

conn = psycopg2.connect(host='localhost', port=5432, user='postgres', password='maestro', dbname='maestro')
cur = conn.cursor()

# Fetch page IDs and embeddings from Supabase (only non-null)
offset = 0
batch = 100
total = 0
updated = 0

while True:
    url = f"{SUPABASE_URL}/rest/v1/pages?select=id,page_embedding&page_embedding=not.is.null&limit={batch}&offset={offset}"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"Error: {resp.status_code} {resp.text[:200]}")
        break
    rows = resp.json()
    if not rows:
        break
    
    for row in rows:
        pid = row['id']
        emb = row['page_embedding']
        if emb:
            # emb comes as a string like "[0.1, 0.2, ...]"
            try:
                cur.execute("UPDATE pages SET page_embedding = %s WHERE id = %s", (emb, pid))
                if cur.rowcount > 0:
                    updated += 1
            except Exception as e:
                print(f"Error on {pid}: {str(e)[:80]}")
                conn.rollback()
        total += 1
    
    conn.commit()
    offset += batch
    print(f"  Processed {total} pages, updated {updated}...")
    
    if len(rows) < batch:
        break

conn.commit()
cur.close()
conn.close()
print(f"Done! Updated {updated}/{total} embeddings.")
