# Local Development Setup — Implementation Plan

> 14 files · 8 requirements · Zero production changes

---

## File Manifest

| # | File | Action | Req |
|---|------|--------|-----|
| 1 | `docker-compose.yml` (root) | CREATE | R1 |
| 2 | `scripts/init-db.sql` | CREATE | R1 |
| 3 | `services/api/app/config.py` | MODIFY (1 line) | R2 |
| 4 | `services/api/requirements.txt` | MODIFY (add python-dotenv) | R2 |
| 5 | `services/api/alembic/env.py` | MODIFY (add dotenv loading) | R2 |
| 6 | `services/api/.env.local` | CREATE (gitignored) | R2 |
| 7 | `apps/web/.env.local` | CREATE (gitignored) | R2 |
| 8 | `scripts/seed-local-db.ps1` | CREATE | R3 |
| 9 | `services/api/app/services/debug_trace.py` | CREATE | R6 |
| 10 | `services/api/app/routers/queries.py` | MODIFY (add debug trace call) | R6 |
| 11 | `.gitignore` | MODIFY (add debug/ dir) | R6 |
| 12 | `scripts/dev.ps1` | CREATE | R7 |
| 13 | `services/api/.env.example` | MODIFY (update template) | R8 |
| 14 | `README.md` | MODIFY (add local dev section) | R8 |

---

## Step 1 · R1 — Docker Compose + pgvector Init

### 1a. Create `docker-compose.yml` (repo root)

```yaml
version: "3.8"
services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: maestro-postgres
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: maestro
      POSTGRES_DB: maestro
    ports:
      - "5432:5432"
    volumes:
      - maestro_pgdata:/var/lib/postgresql/data
      - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/01-init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d maestro"]
      interval: 5s
      timeout: 5s
      retries: 10
volumes:
  maestro_pgdata:
```

**Why `pgvector/pgvector:pg16`**: Ships the vector extension pre-built. Alembic migration `20260131_130000` creates `Vector(1024)` columns — the extension must exist first.

### 1b. Create `scripts/init-db.sql`

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Runs via Docker's `/docker-entrypoint-initdb.d/` mechanism on first container creation (empty volume only). This cannot go in an alembic migration because the existing migration `20260131_130000` already exists without it and modifying it would break checksums.

---

## Step 2 · R2 — Backend .env.local Support

### 2a. Modify `services/api/app/config.py` (line 27)

```python
# BEFORE (line 27)
env_file=".env",

# AFTER
env_file=(".env", ".env.local"),
```

pydantic-settings v2.1+ supports a tuple of files. Later files override earlier ones. When `.env.local` doesn't exist (production on Railway), it's silently skipped. **Zero production impact.**

### 2b. Modify `services/api/requirements.txt`

Add after the `pydantic-settings>=2.1.0` line:

```
python-dotenv>=1.0.0
```

Already an implicit dependency of pydantic-settings, but needed explicitly for the alembic env.py change below.

### 2c. Modify `services/api/alembic/env.py`

Insert **before** `config = context.config` (line 19), after the model imports:

```python
# Load .env and .env.local for alembic CLI (pydantic-settings handles this for
# the app, but alembic runs standalone and its get_url() uses os.getenv directly)
from pathlib import Path
try:
    from dotenv import load_dotenv
    _api_dir = Path(__file__).resolve().parent.parent
    _env_file = _api_dir / ".env"
    _env_local = _api_dir / ".env.local"
    if _env_file.exists():
        load_dotenv(_env_file, override=False)
    if _env_local.exists():
        load_dotenv(_env_local, override=True)
except ImportError:
    pass  # python-dotenv not installed; env vars must be set externally
```

**Why**: Alembic's `get_url()` (line 29) calls `os.getenv("DATABASE_URL")` and `os.getenv("DB_HOST")` directly. Without dotenv loading, `alembic upgrade head` cannot find the local DB credentials from `.env.local`.

### 2d. Create `services/api/.env.local` (gitignored, never committed)

```env
# Local Postgres (Docker)
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=maestro
DB_NAME=maestro

# Auth bypass — Sean's real Supabase user ID (data associations work)
DEV_USER_ID=081745ac-5892-4e79-aed9-1624ff4ad722

# Supabase (keep production values for Storage access)
SUPABASE_URL=https://ybyqobdyvbmsiehdmxwp.supabase.co
SUPABASE_SERVICE_KEY=<copy from services/api/.env>
SUPABASE_JWT_SECRET=<copy from services/api/.env>

# AI Services
GEMINI_API_KEY=<copy from services/api/.env>
VOYAGE_API_KEY=<copy from services/api/.env>

# CORS
FRONTEND_URL=http://localhost:3000
```

Already gitignored by root `.gitignore` line 10: `.env.local`.

---

## Step 3 · R2 — Frontend .env.local

### 3a. Create `apps/web/.env.local` (gitignored)

```env
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=https://ybyqobdyvbmsiehdmxwp.supabase.co
VITE_SUPABASE_ANON_KEY=<copy from apps/web/.env>
```

**Zero code changes needed.** Vite natively loads `.env.local` and overrides `.env`. The API client (`src/lib/api.ts:4`) reads `import.meta.env.VITE_API_URL`. CORS in `main.py:44-51` already allows both `localhost:3000` and `localhost:5173`.

---

## Step 4 · R3 — Data Seeding Script

### 4a. Create `scripts/seed-local-db.ps1`

PowerShell script that:

1. Uses `pg_dump` against Supabase production with these flags:
   - `--data-only` (schema comes from alembic migrations)
   - `--inserts` (Windows line-ending compatible, avoids COPY issues)
   - `--no-owner --no-acl` (avoid permission issues on local)
2. Explicit table list (avoids Supabase internal tables like `auth.*`, `storage.*`):
   ```
   projects, disciplines, pages, pointers, pointer_references,
   conversations, queries, query_pages, usage_events, user_usages,
   processing_jobs, project_memory_files
   ```
3. Truncates local tables in reverse dependency order before restore
4. Restores with `psql` into local Docker Postgres
5. Cleans up dump file after restore

**Parameters**: `$SupabaseHost`, `$SupabasePort`, `$SupabaseUser`, `$SupabaseDb`, `$LocalHost`, `$LocalPort`, `$LocalUser`, `$LocalDb` (all with defaults matching the requirements doc)

**pg_dump availability**: Docker Desktop doesn't include `pg_dump`. Document two options:
- (a) Install PostgreSQL 16 client tools separately (adds `pg_dump`/`psql` to PATH)
- (b) Alternative Python seeding script using psycopg2 (read from prod, write to local)

**Embeddings**: Included by default. `page_embedding` (Vector 1024) and `pointer.embedding` (Vector 1024) are just columns in the dump. No special handling needed.

**RLS**: Local Postgres user `postgres` is a superuser — bypasses RLS automatically. No action needed.

---

## Step 5 · R6 — Debug Trace File

### 5a. Create `services/api/app/services/debug_trace.py`

New module with `write_debug_trace()`:

```python
def write_debug_trace(
    query_text: str,
    mode: str,
    trace: list[dict],
    usage: dict,
    response_text: str,
    display_title: str | None,
    pages_data: list[dict],
    query_id: str,
    project_id: str,
) -> None:
```

**Smart summarization**:
- Strip base64 image data (replace with `"<base64 N chars>"`)
- Truncate thinking/reasoning text: keep first 500 + last 500 chars
- Truncate code execution snippets to first 200 chars each
- Keep findings in full (they're small)
- Keep response text in full
- Annotated images: count + byte sizes only (no data)

**Rotation**: `last-query.json` → `last-query-1.json` → ... → `last-query-5.json`

**Output dir**: `services/api/debug/` (auto-created via `Path.mkdir(parents=True, exist_ok=True)`)

**Safety**: Entire function wrapped in try/except — never crashes the query pipeline.

### 5b. Modify `services/api/app/routers/queries.py`

**Add import** (top of file, after existing imports ~line 27):
```python
from app.services.debug_trace import write_debug_trace
```

**Add call** in `event_generator()` finally block. Insert after the QueryPage records block (after line 461) and before the token tracking block (before line 464):

```python
            # Write debug trace for local development
            if settings.is_dev_mode:
                try:
                    write_debug_trace(
                        query_text=data.query,
                        mode=data.mode,
                        trace=stored_trace,
                        usage={
                            "inputTokens": usage_input_tokens,
                            "outputTokens": usage_output_tokens,
                            "totalTokens": total_tokens,
                        },
                        response_text=response_text,
                        display_title=display_title,
                        pages_data=pages_data,
                        query_id=query_id,
                        project_id=str(project_id),
                    )
                except Exception as e:
                    logger.warning(f"Failed to write debug trace: {e}")
```

Gated on `settings.is_dev_mode` (`config.py:80-82`) — only True when `DEV_USER_ID` is set.

### 5c. Modify `.gitignore` (root)

Append at end of file:
```
# Debug traces (local dev)
services/api/debug/
```

---

## Step 6 · R7 — One-Command Startup

### 6a. Create `scripts/dev.ps1`

PowerShell script:

```
[1/7] Check Docker Desktop — start if not running (60s timeout)
[2/7] docker compose up -d (from repo root)
[3/7] Wait for maestro-postgres healthcheck (30s timeout)
[4/7] pip install -q -r requirements.txt (in services/api/venv)
[5/7] alembic upgrade head (from services/api/)
[6/7] Start-Process powershell — new terminal: activate venv, uvicorn --reload --port 8000
[7/7] Start-Process powershell — new terminal: cd apps/web, pnpm dev
Print URLs: backend :8000, frontend :3000, postgres :5432, debug trace path
```

Backend and frontend run in separate PowerShell windows (not background jobs) so logs are visible.

---

## Step 7 · R8 — Documentation

### 7a. Modify `services/api/.env.example`

Replace with comprehensive template:
```env
# Database — local Docker Postgres
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=maestro
DB_NAME=maestro

# Dev mode — bypasses JWT auth
DEV_USER_ID=your-supabase-user-uuid-here

# Supabase (keep production values for Storage)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret

# AI Services
GEMINI_API_KEY=your-gemini-key
VOYAGE_API_KEY=your-voyage-key
# ANTHROPIC_API_KEY=your-anthropic-key
# OPENROUTER_API_KEY=your-openrouter-key

# CORS
FRONTEND_URL=http://localhost:3000
```

### 7b. Modify `README.md`

Add "Local Development Setup" section after existing dev instructions:
- Prerequisites: Docker Desktop, Python 3.13+ venv, Node v22+ / pnpm, PostgreSQL client tools
- Quick start: `.\scripts\dev.ps1` then `.\scripts\seed-local-db.ps1`
- Manual steps for each component
- `.env.local` file locations and purpose
- Debug trace location and rotation

---

## Key Technical Decisions

| Decision | Rationale |
|----------|-----------|
| `.env.local` via pydantic-settings tuple | 1 line change, zero production risk, native support in v2.1+ |
| Dotenv loading in alembic env.py | Alembic uses `os.getenv()` directly, doesn't read .env files |
| Docker init script for pgvector | Can't modify existing alembic migration checksums |
| `pg_dump --data-only --inserts` | Schema from alembic, `--inserts` avoids Windows COPY issues |
| Debug trace gated on `is_dev_mode` | Never runs in production |
| Separate `debug_trace.py` module | Keeps the 4800-line `agent.py` untouched |

## Pitfalls & Mitigations

| Risk | Mitigation |
|------|-----------|
| pgvector extension missing | `scripts/init-db.sql` via Docker entrypoint |
| `engine.py:62` eager init crashes without DB | Dev script ensures Postgres healthy first |
| RLS blocks local queries | `postgres` superuser bypasses RLS |
| `pg_dump` not on PATH | Document PostgreSQL client tools install |
| `get_settings()` LRU-cached with stale values | `.env.local` loaded before first call |
| Vite port mismatch (3000 vs 5173) | CORS allows both; `vite.config.ts` forces 3000 |
