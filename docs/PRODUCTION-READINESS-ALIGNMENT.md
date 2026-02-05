# Production Readiness Alignment — `feature/local-dev-setup` → `main`

## Intent

The `feature/local-dev-setup` branch contains TWO categories of changes:
1. **Local dev infrastructure** — Docker, scripts, dev mode bypasses (NOT for production)
2. **Maestro Orchestrator + UI** — New features gated behind `MAESTRO_ORCHESTRATOR=False` flag (FOR production)

**Goal:** Make this branch safe to merge into `main` so Railway auto-deploys without breaking anything. The orchestrator stays dormant until the `MAESTRO_ORCHESTRATOR` env var is set to `True` in Railway.

---

## Architecture Discovery

### Deployment
- **Backend:** Railway auto-deploys from `main` (FastAPI/uvicorn)
- **Frontend:** Vercel auto-deploys from `main` (React/Vite)
- **Database:** Supabase Postgres (remote, shared between local and prod)
- **Storage:** Supabase Storage (remote)

### Feature Flag Pattern (existing)
The codebase already uses boolean flags in `app/config.py`:
```python
MED_MODE_REGIONS = True
DEEP_MODE_VISION_V2 = True
DEEP_MODE_V3_AGENTIC = True
DEEP_MODE_V4_UNCONSTRAINED = True
MAESTRO_ORCHESTRATOR = False  # NEW — added by this branch
```
These are loaded via `Settings(BaseSettings)` from env vars. Default values are the module-level constants.

### Key Files Modified (36 files, ~4400 lines added)
The branch has 20 commits on top of `main`.

---

## Requirements

### R1: Audit Feature Flag Gating

**Every code path that touches orchestrator logic MUST be unreachable when `MAESTRO_ORCHESTRATOR=False`.**

Check these specific locations:

1. **`services/api/app/routers/queries.py`** — The orchestrator routing logic:
   ```python
   use_orchestrator = data.learning_mode or bool(getattr(settings, "maestro_orchestrator", False))
   ```
   - When `maestro_orchestrator=False` AND `learning_mode=False` (the default), `use_orchestrator` is `False`
   - The `event_source` falls through to `run_agent_query()` (existing behavior)
   - **Verify:** No other code path in this file references orchestrator functions unconditionally

2. **`services/api/app/models/__init__.py`** — Imports `ProjectMemoryFile` and `LearningEvent`
   - These are SQLAlchemy model classes. Importing them is fine — they just define table mappings
   - **BUT:** If the tables don't exist in production Supabase, and SQLAlchemy tries to query them, it will 500
   - **Verify:** No code queries these tables unless `use_orchestrator=True`

3. **`services/api/app/services/core/big_maestro.py`** — The orchestrator module (838 lines)
   - This file is imported in `queries.py` at the top level: `from app.services.core.big_maestro import run_maestro_query`
   - **Verify:** The import itself doesn't cause side effects (no module-level code that runs on import, no database calls, no network calls). Importing a module with function definitions is safe.

4. **`services/api/app/services/memory.py`** — Memory CRUD (388 lines)
   - Imported by `big_maestro.py`
   - **Verify:** Same as above — import is safe, no module-level side effects

5. **`services/api/app/services/debug_trace.py`** — Debug trace writer
   - Only called inside `if settings.is_dev_mode:` block in `queries.py`
   - **Verify:** `is_dev_mode` is `False` in production (it checks for `DEV_USER_ID` env var which is not set in Railway)

6. **`services/api/app/services/providers/gemini.py`** — Added `memory_context=""` parameter to 3 functions + `{memory_section}` in prompt templates
   - These are optional kwargs with default `""`
   - When not passed (existing code paths), `memory_section` resolves to empty string
   - **Verify:** The `{memory_section}` placeholder is properly handled — when empty, it should produce no visible change in the prompt. Check that there isn't an extra blank line or formatting issue.

### R2: Remove or Guard Local-Dev-Only Changes

These changes are ONLY for local development and should either be reverted or made safe for production:

1. **`apps/web/src/App.tsx`** — Dev mode auth bypass + console.log statements
   - The `VITE_DEV_MODE` check is safe (env var not set in Vercel production)
   - **BUT:** Remove the `console.log('[DEV]...')` statements — they leak implementation details in production browser console
   - Lines to remove: `console.log('[DEV] Auth bypassed...')`, `console.log('[DEV] loadProject starting...')`, `console.log('[DEV] loadProject got projects...')`

2. **`apps/web/src/lib/api.ts`** — Dev mode auth skip
   - The `VITE_DEV_MODE` check is safe (env var not set in Vercel production)
   - **Verify:** When `VITE_DEV_MODE` is not set, the code path is identical to `main`. The try/catch around `supabase.auth.getSession()` is actually a minor improvement (more resilient).

3. **`services/api/app/config.py`** — `.env.local` support added to `env_file`
   - Changed from `env_file=".env"` to `env_file=(".env", ".env.local")`
   - **This is safe for production** — if `.env.local` doesn't exist, pydantic-settings ignores it. Railway sets env vars directly, not via files.

4. **`services/api/alembic/env.py`** — dotenv loading for alembic CLI
   - Added try/except import of `load_dotenv` for `.env` and `.env.local`
   - **This is safe for production** — if files don't exist, nothing happens. If `python-dotenv` isn't installed, the except passes silently.

5. **`services/api/requirements.txt`** — Added `python-dotenv>=1.0.0`
   - **This is fine for production** — lightweight dependency, already a transitive dep of pydantic-settings

### R3: Database Migration for New Models

**CRITICAL.** Two new SQLAlchemy models were added:
- `ProjectMemoryFile` — table `project_memory_files`
- `LearningEvent` — table `learning_events`

These tables do **NOT** exist in the production Supabase database.

**Options (pick one):**
1. **Create an alembic migration** that adds these tables — run it against production after merge
2. **Defer the migration** — but then ensure NO code path can query these tables when `MAESTRO_ORCHESTRATOR=False`. If any import or startup code touches them, the app will crash.

**Recommended:** Option 2 for now. The models are only used inside `big_maestro.py` and `memory.py`, which are only called when `use_orchestrator=True`. Verify this is airtight.

**Action:** Check that `alembic/env.py` importing these models doesn't trigger table creation or validation at startup. SQLAlchemy model imports just register metadata — they don't CREATE tables unless `Base.metadata.create_all()` is called.

### R4: Frontend Safety Audit

New frontend components:
- `EvolvedResponse.tsx` (96 lines)
- `PageWorkspace.tsx` (97 lines)
- `WorkspacePageCard.tsx` (239 lines)
- `useQueryManager.ts` (81 lines)
- `useWorkspacePages.ts` (264 lines)

And modifications to:
- `FeedViewer.tsx` — renders PageWorkspace
- `MaestroMode.tsx` — integrates useWorkspacePages
- `ThinkingSection.tsx` — enhanced with new event types
- `types/query.ts` — new type definitions

**Verify:**
1. These components only render when orchestrator SSE events are received. If the backend never sends `page_state`, `response_update`, or `learning` events (because orchestrator is off), these components should be inert.
2. No new components crash on `undefined`/`null` data from the existing event stream.
3. The `useQueryManager` hook — does it REPLACE or AUGMENT existing SSE handling? If it replaces, it must handle ALL existing event types correctly.
4. **TypeScript compilation** — run `npx tsc --noEmit` in `apps/web/` to verify no type errors that would break the Vercel build.

### R5: Local-Dev-Only Files (Keep but Don't Ship Logic Bugs)

These files are local dev infrastructure. They're fine to keep in the repo:
- `docker-compose.yml`
- `scripts/dev.ps1`
- `scripts/init-db.sql`
- `scripts/init-local-schema.sql`
- `scripts/seed-local-db.ps1`
- `docs/LOCAL-DEV-SETUP.md`
- `docs/LOCAL-DEV-IMPLEMENTATION-PLAN.md`
- `docs/MAESTRO-ORCHESTRATOR-ALIGNMENT.md`
- `docs/AGENT-WORKSPACE-PHASE1.md`

**No action needed** — these don't affect production runtime.

### R6: Verify Existing Tests (if any)

Check if there are any existing tests in the repo. If yes, run them to make sure nothing is broken.

```bash
cd services/api && python -m pytest  # if tests exist
cd apps/web && npm test  # if tests exist
```

### R7: Clean Up Console Logs

Remove all `console.log('[DEV]...')` statements from frontend code. These were added for local debugging and shouldn't ship to production.

Search for: `console.log('[DEV]` in `apps/web/src/`

---

## Constraints — DO NOT BREAK

1. **Existing query flow** — When `MAESTRO_ORCHESTRATOR=False`, the entire query pipeline (Fast/Med/Deep) must work identically to current `main`
2. **Authentication** — Supabase auth must work normally in production (no dev bypasses activating)
3. **SSE streaming** — Existing event types (`thinking`, `tool_call`, `tool_result`, `done`, `error`, `annotated_image`, `code_execution`, `code_result`) must still work
4. **No new required env vars** — The merge should not require ANY new env vars in Railway/Vercel. Everything new must have safe defaults.
5. **No database schema changes required at deploy time** — New tables should not be referenced until explicitly enabled
6. **Vercel build must pass** — TypeScript compilation cannot have errors

---

## Implementation Order

1. **R1** — Audit feature flag gating (read-only, report findings)
2. **R3** — Verify no startup-time table access for new models
3. **R4** — Frontend safety audit (TypeScript check, component behavior)
4. **R7** → **R2** — Remove console.logs, verify dev-mode guards
5. **R6** — Run any existing tests
6. **R5** — Confirm local-dev files are inert

**Output:** After completing all checks, produce a summary of:
- ✅ Items verified safe
- ⚠️ Items that need changes (with exact file:line and fix)
- Apply any necessary fixes (remove console.logs, fix any flag gating issues)
- Commit changes with message: `fix: production-readiness cleanup for merge to main`

---

## Environment

- **OS:** Windows 10 (x64)
- **Node:** v22.20.0
- **Python:** Check with `python --version` in `services/api/`
- **Repo:** `C:\Users\Sean Schneidewent\Maestro-Super`
- **Branch:** `feature/local-dev-setup`
- **Package manager:** npm (frontend), pip (backend)
