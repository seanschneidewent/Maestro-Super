# Local Development Setup — Intent & Requirements

## Intent

Set up Maestro-Super for full local development on Windows (Sean's PC). The goal is fast iteration: run a query, see every tool result, change code, rerun. No deploying to Railway to test changes. No waiting for Vercel previews.

**Current state:** Backend runs on Railway (production), frontend on Vercel. Both point to Supabase (hosted Postgres + Storage). There is no working local dev setup.

**Target state:** Backend runs locally (uvicorn), frontend runs locally (vite dev), both talk to a local Postgres with production data cloned in. File storage still uses Supabase (no need to replicate storage locally). Debug trace file written on every query for Ember to read.

---

## Architecture Discovery

### Stack
| Component | Production | Local Target |
|-----------|-----------|--------------|
| **Backend** | Railway (FastAPI + uvicorn) | `uvicorn app.main:app --reload` on localhost:8000 |
| **Frontend** | Vercel (React + Vite) | `pnpm dev` on localhost:5173 |
| **Database** | Supabase Postgres (hosted) | Local Postgres 16 via Docker |
| **File Storage** | Supabase Storage (bucket: `project-files`) | **Keep using Supabase Storage** (files are large, no need to replicate) |
| **Auth** | Supabase JWT | `DEV_USER_ID` bypass (already implemented) |
| **AI APIs** | Gemini, Claude, Voyage, OpenRouter | Same API keys (cloud services, no local hosting) |

### Database Dependencies
- **PostgreSQL 16** — required (not SQLite)
- **pgvector extension** — required for `page_embedding` (Vector(1024)) and `<=>` cosine distance operator
- **JSONB columns** — used extensively (regions, master_index, sheet_info, ocr_data, etc.)
- **UUID type** — `CAST(:project_id AS uuid)` in raw SQL queries
- **15 alembic migrations** — must all run clean on local Postgres

### Postgres-Specific Features Used
1. `pgvector.sqlalchemy.Vector(1024)` on `Page.page_embedding` and `Pointer.embedding`
2. `<=>` operator for cosine distance in raw SQL (`search.py:vector_search_pages`)
3. `CAST(:project_id AS uuid)` in raw SQL
4. `sqlalchemy.dialects.postgresql.JSONB` on 10+ columns
5. `sqlalchemy.dialects.postgresql.UUID` in conversation model
6. Connection pooling params (keepalives, timeouts) in engine.py

### Storage Architecture
- Backend uses `supabase-py` client for all file ops (upload, download, signed URLs)
- Frontend uses `@supabase/supabase-js` for direct storage access (page images, PDFs)
- Files stored in `project-files` bucket with paths like `projects/{id}/file.pdf` and `page-images/{project_id}/{page_id}.png`
- **Decision: Keep using remote Supabase Storage.** Files are multi-MB PDFs and PNGs. No benefit to local replication. Both local frontend and backend can still hit Supabase Storage directly.

### Auth
- `DEV_USER_ID` env var already implements full auth bypass
- When set, `get_current_user()` returns `User(id=dev_user_id, email="dev@local.test")`
- Frontend needs a valid Supabase session for storage access → **keep using production Supabase auth** (anon key) even locally
- Backend auth is bypassed via `DEV_USER_ID`

### API Keys Required
| Key | Service | Used For |
|-----|---------|----------|
| `GEMINI_API_KEY` | Google AI | Brain Mode processing, Deep Mode V4, Fast Mode routing |
| `VOYAGE_API_KEY` | Voyage AI | Embedding generation (1024-dim vectors) |
| `ANTHROPIC_API_KEY` | Anthropic | Claude-based query agent (optional path) |
| `OPENROUTER_API_KEY` | OpenRouter | Kimi K2 query agent (optional path) |

### Frontend Config
- `VITE_API_URL` — must point to `http://localhost:8000` for local dev
- `VITE_SUPABASE_URL` — keep production Supabase URL (for storage + auth)
- `VITE_SUPABASE_ANON_KEY` — keep production anon key

---

## Requirements

### R1: Local Postgres via Docker
- Docker Compose file at repo root: `docker-compose.yml`
- Postgres 16 with pgvector extension pre-installed
- Persistent volume for data (survives container restarts)
- Exposed on `localhost:5432`
- Default credentials: `postgres` / `maestro` / `maestro`
- Health check so dependent services wait for ready

### R2: Local Environment Files
- `services/api/.env.local` — local dev overrides (gitignored)
  - `DB_HOST=localhost`, `DB_PORT=5432`, `DB_USER=postgres`, `DB_PASSWORD=maestro`, `DB_NAME=maestro`
  - `DEV_USER_ID=081745ac-5892-4e79-aed9-1624ff4ad722` (Sean's real user ID — so data associations work)
  - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` — keep production values (for storage)
  - `GEMINI_API_KEY`, `VOYAGE_API_KEY` — real keys
  - `FRONTEND_URL=http://localhost:5173`
- `apps/web/.env.local` — local dev overrides (gitignored)
  - `VITE_API_URL=http://localhost:8000`
  - `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` — keep production values

### R3: Data Seeding Script
- Script to clone production data into local Postgres
- **Approach A (preferred):** Use Supabase CLI or `pg_dump` against the Supabase connection to dump schema + data, then `pg_restore` into local
- **Approach B:** Python script that queries Supabase REST API for projects/disciplines/pages (without embeddings — those are huge) and inserts into local DB
- Must handle: projects, disciplines, pages (with all JSONB columns), conversations, queries
- Embeddings can be re-generated locally with Voyage API if needed, or pulled from prod
- **Critical:** Page `file_path` values must stay the same (they reference Supabase Storage paths)

### R4: Backend Startup
- Load `.env.local` instead of `.env` when present (pydantic-settings already supports this via `env_file` priority)
- Run alembic migrations against local Postgres
- Start uvicorn with `--reload` for hot-reload during development
- Install missing pip packages: `pgvector`, `voyageai`
- Single command to start: `make dev-api` or equivalent

### R5: Frontend Startup  
- Load `.env.local` overrides (Vite handles this natively — `.env.local` overrides `.env`)
- Start vite dev server
- Single command: `pnpm dev` (already works)

### R6: Debug Trace File
- On every query completion (fast/med/deep), write a compact debug summary to `services/api/debug/last-query.json`
- Smart summarization: strip base64 image data, truncate huge JSONB blobs, keep:
  - Query text, mode, timestamp
  - Pages selected (IDs + names only)
  - Search mission (if deep mode)
  - Router result (if fast/deep)
  - Thinking text (first 500 chars + last 500 chars)
  - Code execution snippets (first 200 chars each)
  - Findings (full — these are small)
  - Response text (full)
  - Annotated images: count + byte sizes (not the base64)
  - Token usage + timing
  - Errors
- Rotating: keep last 5 queries as `last-query-1.json` through `last-query-5.json`
- Gitignored

### R7: One-Command Startup
- `make dev` or `scripts/dev.ps1` that:
  1. Starts Docker Postgres (if not running)
  2. Waits for Postgres health check
  3. Runs alembic migrations
  4. Starts backend (uvicorn --reload) in background
  5. Starts frontend (pnpm dev) in background
  6. Prints URLs and status

### R8: Documentation
- Update `README.md` with local dev setup instructions
- Update `services/api/.env.example` with local Postgres example
- Document the data seeding process

---

## Constraints

1. **Do NOT modify production behavior.** All changes must be additive and behind local-dev checks or separate files.
2. **Do NOT copy Supabase Storage locally.** Keep using remote storage. Only the database is local.
3. **Do NOT change the database schema.** Local Postgres must run the same migrations as production.
4. **Do NOT commit secrets.** `.env.local` files must be gitignored.
5. **Keep pydantic-settings loading order.** `.env.local` overrides `.env` — don't break production `.env`.
6. **Windows-compatible.** Sean's dev machine is Windows 10. Scripts must work in PowerShell. Docker Desktop is installed (service exists but may need starting).

---

## Implementation Order

1. **Docker Compose** — Postgres 16 + pgvector container
2. **Environment files** — `.env.local` for backend and frontend
3. **pip installs** — `pgvector`, `voyageai` in local venv
4. **Alembic migrations** — run against local Postgres
5. **Data seeding** — clone production data
6. **Debug trace** — `_write_debug_trace()` in agent.py
7. **Startup script** — `scripts/dev.ps1`
8. **Test** — run a query end-to-end locally
9. **Documentation** — README updates

---

## Environment Details

- **OS:** Windows 10 (10.0.26200, x64)
- **Docker:** 28.5.1 (Docker Desktop, service currently stopped)
- **Python:** 3.13.5 (venv at `services/api/venv/`)
- **Node:** v22.20.0
- **Package manager:** pnpm (frontend)
- **Existing venv packages:** FastAPI 0.128, SQLAlchemy 2.0.45, psycopg2-binary 2.9.11, google-genai 1.56, supabase 2.27 — **missing:** pgvector, voyageai

---

## Supabase Production Credentials (for data seeding + storage access)

- **Project URL:** `https://ybyqobdyvbmsiehdmxwp.supabase.co`
- **DB Host:** `aws-0-us-west-2.pooler.supabase.com`
- **DB Port:** 5432
- **DB User:** `postgres.ybyqobdyvbmsiehdmxwp`
- **DB Password:** `SchneidewentM1G@r@nd`
- **DB Name:** `postgres`
- **Service Key:** (in services/api/.env)
- **Anon Key:** (in apps/web/.env)

---

*This document is the source of truth for Claude Code implementation. Follow the requirements (R1-R8) in order. Ask before deviating from constraints.*
