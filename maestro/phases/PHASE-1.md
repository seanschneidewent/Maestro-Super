# Phase 1: Enhanced Knowledge (Pass 2 + Schema Foundation)

## Context

Read `maestro/MAESTRO-ARCHITECTURE-V3.md` — it is the alignment doc for the entire V3 architecture. This phase implements the foundation that everything else builds on.

**This is Phase 1 — there are no prior phase commits to reference.**

## Goal

1. **Schema foundation** — Create all new Supabase tables and columns needed for V3. This means future phases don't need migrations.
2. **Pass 2 enrichment pipeline** — Background worker that takes each Pointer created by Pass 1 and enriches it with a rich markdown description, structured cross-references, and vector embeddings.
3. **Default Experience seeding** — When a project is created, seed the default Experience files so they exist from day one.

## What This Phase Delivers

After this phase ships:
- Every Brain Mode upload produces Pointers with `enrichment_status=pending`
- A background worker picks up pending Pointers, downloads the cropped image, sends it to Gemini with the sheet reflection as context, and writes back a rich markdown description + cross-references + embedding
- The `experience_files` and `sessions` tables exist in Supabase (empty, but ready for Phase 2+)
- New projects get seeded with default Experience files (routing_rules.md, corrections.md, preferences.md, schedule.md, gaps.md)
- The existing system is completely unaffected — this is purely additive

## Architecture Reference

See the V3 alignment doc sections:
- **"Code Expression: New Supabase Tables"** — SQL for `experience_files` and `sessions` tables
- **"Code Expression: Pass 2 Enrichment Pipeline"** — `EnrichmentInput`, `EnrichmentOutput`, `enrich_pointer()`, `run_pass2_worker()` signatures
- **"Code Expression: Pointer Schema Changes"** — new columns on Pointer model + Alembic migration SQL
- **"Code Expression: Experience Injection"** — `seed_default_experience()` function

## Gemini Agentic Vision

Pass 2 uses Gemini with code execution for vision analysis. Reference the official documentation:
**https://ai.google.dev/gemini-api/docs/code-execution#python**

The existing Pass 1 implementation is in `services/api/app/services/providers/gemini.py` — the `analyze_sheet_brain_mode()` function. Pass 2 follows the same pattern but operates on cropped images (individual Pointer regions) rather than full pages.

## Detailed Requirements

### R1: Alembic Migrations

Create migrations for all V3 schema changes:

**Pointer table changes:**
- Add `enrichment_status VARCHAR(20) NOT NULL DEFAULT 'pending'` with index
- Add `cross_references JSONB`
- Add `enrichment_metadata JSONB`
- Backfill: set `enrichment_status = 'complete'` where description IS NOT NULL and embedding IS NOT NULL; set remaining to `'pending'`

**New table: `experience_files`**
- `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- `project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE`
- `path TEXT NOT NULL`
- `content TEXT NOT NULL DEFAULT ''`
- `updated_by_session UUID`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `UNIQUE(project_id, path)`
- Index on `project_id`

**New table: `sessions`**
- `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- `project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE`
- `user_id TEXT NOT NULL`
- `session_type TEXT NOT NULL CHECK (session_type IN ('workspace', 'telegram'))`
- `workspace_id UUID`
- `workspace_name TEXT`
- `maestro_messages JSONB NOT NULL DEFAULT '[]'::jsonb`
- `learning_messages JSONB NOT NULL DEFAULT '[]'::jsonb`
- `workspace_state JSONB DEFAULT '{"displayed_pages":[],"highlighted_pointers":[],"pinned_pages":[]}'::jsonb`
- `status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'idle', 'closed'))`
- `last_active_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- Indexes on `project_id`, `user_id`, and `status WHERE status = 'active'`

### R2: SQLAlchemy Models

**Add to existing `services/api/app/models/pointer.py`:**
- `enrichment_status` column (String(20), default='pending', indexed)
- `cross_references` column (JSONB, nullable)
- `enrichment_metadata` column (JSONB, nullable)

**Create `services/api/app/models/experience_file.py`:**
- SQLAlchemy model matching the `experience_files` table schema above

**Create `services/api/app/models/session.py`:**
- SQLAlchemy model matching the `sessions` table schema above

**Register both new models in `services/api/app/models/__init__.py`**

### R3: Pass 2 Enrichment Agent

**Create `services/api/app/services/core/pass2_enrichment.py`:**

The enrichment function:
- Takes: pointer_id, cropped_image_bytes, sheet_reflection, page_name, discipline_name, pointer_title
- Calls Gemini (same model as Brain Mode, vision + code execution, thinking=high) with the cropped image
- System prompt instructs Gemini to extract EVERYTHING: dimensions, notes, spec callouts, line items, cross-references to other sheets/details
- Context includes the sheet_reflection from the parent page so Gemini understands what this detail is within the larger sheet
- Returns: rich_description (markdown), cross_references (list of strings), embedding_text (the text to embed)
- See https://ai.google.dev/gemini-api/docs/code-execution#python for Gemini code execution setup

The enrichment prompt should instruct Gemini to:
- Read every piece of text visible in the cropped image
- Extract all dimensions with units
- Extract all specification callouts
- List all cross-references to other sheets or details
- Extract table contents line by line if the region contains a table/schedule
- Organize the output as structured markdown
- Note anything ambiguous or partially visible

### R4: Background Worker

**Create `services/api/app/services/core/pass2_worker.py`:**

- `run_pass2_worker()` — async function that runs as a background task
- On startup: `UPDATE pointers SET enrichment_status = 'pending' WHERE enrichment_status = 'processing'` (handles restart mid-enrichment)
- Poll loop:
  1. Query for Pointers with `enrichment_status = 'pending'` ordered by `created_at`, limit batch_size (e.g., 10)
  2. If none found, sleep 5 seconds, then poll again
  3. For each Pointer:
     a. Set `enrichment_status = 'processing'`
     b. Load the parent page (need `sheet_reflection`, `page_name`, `discipline_name`)
     c. Download cropped image from Supabase storage using `pointer.png_path`
     d. Call `enrich_pointer()`
     e. Write `description` (rich markdown), `cross_references`, and `embedding` back to the Pointer row
     f. Set `enrichment_status = 'complete'`
     g. On any failure: set `enrichment_status = 'failed'`, log the error
- Concurrency: process up to 3 Pointers concurrently using `asyncio.gather()` with semaphore
- Respect Gemini rate limits (existing retry infrastructure in `app/utils/retry.py`)

**Register the worker in `services/api/app/main.py`:**
- Use FastAPI `lifespan` or `on_event("startup")` to launch `run_pass2_worker()` as a background task
- The worker runs for the lifetime of the server process

### R5: Embedding Generation

After enrichment, generate a vector embedding from the rich description:
- Use the existing Voyage embedding infrastructure in `services/api/app/services/providers/voyage.py`
- Embed the `rich_description` text
- Write the 1024-dim vector to the Pointer's `embedding` column
- This happens inside the enrichment flow (after Gemini returns, before marking 'complete')

### R6: Hook Pass 2 Into Pass 1

After Pass 1 creates Pointers (in the existing processing pipeline), ensure they have:
- `enrichment_status = 'pending'` (default from migration)
- `png_path` set (the cropped image — Pass 1 already does this)

The background worker will automatically pick them up. No changes to Pass 1 logic needed beyond ensuring the new columns have correct defaults.

### R7: Default Experience Seeding

**Create `services/api/app/services/v3/experience.py`:**

`seed_default_experience(project_id, db)` function:
- Creates 5 rows in `experience_files` for the given project:
  - `routing_rules.md` — starter content with section headers (Default Routes, Extended Knowledge, Learned Patterns)
  - `corrections.md` — empty with header
  - `preferences.md` — empty with header
  - `schedule.md` — empty with header
  - `gaps.md` — empty with header
- Uses INSERT ... ON CONFLICT DO NOTHING (idempotent)

**Hook into project creation:**
- Find where projects are created (likely `services/api/app/routers/projects.py`)
- After project creation, call `seed_default_experience(project_id, db)`

### R8: Config Updates

**In `services/api/app/config.py`:**
- Add `PASS2_MODEL` constant (default: same as `BRAIN_MODE_MODEL`)
- Add `pass2_model` setting
- Add `pass2_max_concurrent` setting (default: 3)
- Add `pass2_poll_interval` setting (default: 5.0 seconds)

## Constraints

- **Do NOT modify Brain Mode Pass 1** — it's working perfectly
- **Do NOT modify or remove any existing query endpoints** — the old system stays functional during Phase 1
- **Do NOT break the existing frontend** — Phase 1 is backend-only
- **Additive schema changes only** — new columns have defaults, new tables are independent
- **The `sessions` and `experience_files` tables are created but empty** — they get populated starting in Phase 2

## File Map

```
NEW FILES:
  services/api/app/models/experience_file.py
  services/api/app/models/session.py
  services/api/app/services/core/pass2_enrichment.py
  services/api/app/services/core/pass2_worker.py
  services/api/app/services/v3/experience.py
  services/api/alembic/versions/YYYYMMDD_HHMMSS_v3_schema_foundation.py

MODIFIED FILES:
  services/api/app/models/pointer.py          (add enrichment_status, cross_references, enrichment_metadata)
  services/api/app/models/__init__.py          (register new models)
  services/api/app/config.py                   (add PASS2_MODEL, pass2 settings)
  services/api/app/main.py                     (launch pass2_worker on startup)
  services/api/app/routers/projects.py         (seed Experience on project creation)
```

## Environment

- **OS:** Windows 10 (dev), Linux (Railway production)
- **Python:** 3.11+
- **Backend:** FastAPI + SQLAlchemy + Supabase (Postgres + pgvector)
- **Gemini docs:** https://ai.google.dev/gemini-api/docs/code-execution#python
- **Repo:** `C:\Users\Sean Schneidewent\Maestro-Super`
- **Backend path:** `services/api/`
