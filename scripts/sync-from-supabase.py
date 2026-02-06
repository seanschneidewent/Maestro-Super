"""
Sync production Supabase data into local Postgres.
Pulls all tables via REST API and inserts into local DB.
"""
import json
import requests
import psycopg2
from psycopg2.extras import execute_values, Json

SUPABASE_URL = "https://ybyqobdyvbmsiehdmxwp.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlieXFvYmR5dmJtc2llaGRteHdwIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NzExOTQ5OSwiZXhwIjoyMDgyNjk1NDk5fQ.qGIVjk8Ay9nnyXgHfDVKHGGDWEbeB7oZI9XPtIoJ1Vo"

LOCAL_DB = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "maestro",
    "dbname": "maestro"
}

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

# Tables in FK-safe order
TABLES = [
    "projects",
    "disciplines",
    "pages",
    "pointers",
    "conversations",
    "queries",
    "project_memory_files",
    "learning_events",
]

# Columns to skip (vectors, binary, or columns that don't exist locally)
SKIP_COLUMNS = {"page_embedding"}


def fetch_all(table: str) -> list[dict]:
    """Fetch all rows from a Supabase table, handling pagination."""
    all_rows = []
    offset = 0
    batch = 1000
    while True:
        url = f"{SUPABASE_URL}/rest/v1/{table}?select=*&limit={batch}&offset={offset}"
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            print(f"  ERROR fetching {table}: {resp.status_code} - {resp.text[:200]}")
            break
        rows = resp.json()
        if not rows:
            break
        all_rows.extend(rows)
        offset += batch
        if len(rows) < batch:
            break
    return all_rows


def get_local_columns(cur, table: str) -> set[str]:
    """Get column names from local Postgres table."""
    cur.execute("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = %s AND table_schema = 'public'
    """, (table,))
    return {row[0] for row in cur.fetchall()}


def sync_table(cur, table: str, rows: list[dict], local_cols: set[str]):
    """Insert rows into local table, mapping only shared columns."""
    if not rows:
        print(f"  {table}: no rows to sync")
        return 0
    
    # Find columns that exist in both source and local
    source_cols = set(rows[0].keys())
    shared_cols = (source_cols & local_cols) - SKIP_COLUMNS
    col_list = sorted(shared_cols)
    
    if not col_list:
        print(f"  {table}: no shared columns!")
        return 0
    
    # Build INSERT with ON CONFLICT DO NOTHING
    cols_str = ", ".join(f'"{c}"' for c in col_list)
    placeholders = ", ".join(["%s"] * len(col_list))
    
    inserted = 0
    for row in rows:
        values = []
        for col in col_list:
            val = row.get(col)
            # Wrap dicts/lists as JSON
            if isinstance(val, (dict, list)):
                val = Json(val)
            values.append(val)
        
        try:
            cur.execute(
                f'INSERT INTO "{table}" ({cols_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING',
                values
            )
            if cur.rowcount > 0:
                inserted += 1
        except Exception as e:
            # Log and continue
            print(f"  Row error in {table}: {str(e)[:100]}")
            cur.connection.rollback()
            continue
    
    return inserted


def main():
    print("=== Syncing Supabase -> Local Postgres ===\n")
    
    conn = psycopg2.connect(**LOCAL_DB)
    conn.autocommit = False
    cur = conn.cursor()
    
    for table in TABLES:
        print(f"\n>> {table}...")
        
        # Check if local table exists
        local_cols = get_local_columns(cur, table)
        if not local_cols:
            print(f"  [!] Table '{table}' not found locally, skipping")
            continue
        
        # Fetch from Supabase
        rows = fetch_all(table)
        print(f"  Fetched {len(rows)} rows from Supabase")
        
        if not rows:
            continue
        
        # Show column mapping
        source_cols = set(rows[0].keys())
        shared = (source_cols & local_cols) - SKIP_COLUMNS
        missing_local = source_cols - local_cols - SKIP_COLUMNS
        missing_remote = local_cols - source_cols
        
        if missing_local:
            print(f"  [!] Skipping remote-only columns: {', '.join(sorted(missing_local)[:5])}")
        
        # Sync
        inserted = sync_table(cur, table, rows, local_cols)
        conn.commit()
        print(f"  [OK] Inserted {inserted}/{len(rows)} rows")
    
    cur.close()
    conn.close()
    print("\n=== Done! ===")


if __name__ == "__main__":
    main()
