# Maestro Orchestrator — Alignment Profile

*For Claude Code implementation. Read this document completely before planning.*

---

## Intent

Transform Maestro's query flow from a monolithic single-Gemini-call deep mode into an **orchestrated parallel agent system** with an evolving response.

**Current state:** `run_agent_query_deep()` does everything — Fast Mode page selection, image loading, then sends ALL pages into ONE `explore_with_agentic_vision_v4()` Gemini call. One call, one response, done.

**Target state:** Big Maestro is the orchestrator. It runs Fast Mode to select pages, spawns parallel per-page Deep agents (each making its own Gemini call), and synthesizes an **evolved response** that updates incrementally as each agent completes. The frontend shows a thinking stream, page workspace with live state transitions, and a single response block that grows richer over time.

**Key principle:** The existing Deep Mode V4 agentic vision becomes a **subfunction** — called once per page instead of once for all pages. We're not rewriting the vision logic, just changing how it's orchestrated.

---

## Architecture Discovery

### Backend — Current Query Flow (`services/api/app/services/core/agent.py`)

`run_agent_query()` dispatches by mode:
- `fast` → `run_agent_query_fast()` — RAG + Gemini page selection, no vision
- `med` → `run_agent_query_med()` — page selection + deterministic region highlights
- `deep` → `run_agent_query_deep()` — the monolithic function we're refactoring

**`run_agent_query_deep()` (line 3645, ~700 lines):**
1. Get project structure summary
2. Route query (Gemini Flash) → get must_terms, preferred_page_types
3. RAG region search + keyword search → candidate page IDs
4. Smart page selection (Gemini Flash) → ordered page IDs (max 5)
5. Expand with cross-references
6. Build search missions (per-page, via `search_missions.py`)
7. Load page images (async, from Supabase storage)
8. Call `explore_with_agentic_vision_v4()` with ALL pages + ALL missions in ONE call
9. Post-process: normalize findings, resolve highlight overlays
10. Yield `done` event with trace, findings, highlights, usage

Steps 1-7 are the **Fast Mode pipeline** (page selection + prep).
Step 8 is the **Deep Mode execution** (single Gemini call).
Steps 9-10 are **post-processing**.

### Backend — Deep Mode V4 (`services/api/app/services/providers/gemini.py`)

`explore_with_agentic_vision_v4()` (line 2531):
- Takes: query, pages (list of dicts with `image_bytes`, `page_id`, `page_name`), search_mission, history/viewing context
- Builds one prompt with ALL page images as parts
- Single `generate_content_stream()` call to Gemini 3 Flash with code execution + thinking
- Streams: thinking, code, code_result, annotated_image, text events
- Returns accumulated text as the response (no structured findings in V4)
- **This function already handles a list of pages — for per-page use, just pass a single-page list**

### Backend — Search Missions (`services/api/app/services/core/search_missions.py`)

`build_search_missions()` returns:
```json
{
  "query": "...",
  "pages": [
    {
      "page_id": "...",
      "page_name": "...",
      "search_targets": ["..."],
      "context": "...",
      "sheet_reflection": "..."
    }
  ]
}
```
**Already per-page.** Each page gets its own search targets and context. Perfect for parallel agents.

### Backend — Big Maestro Learning System (restored files)

Three files restored from git history (commit `8963597`):

**`services/api/app/services/core/big_maestro.py` (467 lines):**
- `detect_teaching_intent(query, previous_response)` → bool
- `classify_learning(query)` → type (routing/truth/preference/agent behavior), file_type, confidence
- `extract_learning_content(query, classification)` → formatted string for memory file
- `process_learning(db, project_id, user_id, query, ...)` → async iterator yielding thinking + learning_complete events
- `run_with_learning(db, project_id, user_id, query, ...)` → entry point: detect teaching, process if yes, else delegate to `run_agent_query()`

**`services/api/app/services/memory.py` (388 lines):**
- `build_memory_context(db, project_id, user_id)` → formatted string for prompt injection
- `get_memory_file_content(db, project_id, user_id, file_type)` → str
- `upsert_memory_file(db, project_id, user_id, file_type, content)`
- `append_to_memory_file(db, project_id, user_id, file_type, content, section)`
- `log_learning_event(db, ...)` → creates learning_events row
- File types: core, routing, preferences, memory, learning, fast_context, med_context, deep_context

**`services/api/app/models/project_memory.py` (104 lines):**
- `ProjectMemoryFile` model — project_id, user_id, file_type, file_content, timestamps
- `LearningEvent` model — project_id, user_id, event_type, classification, correction_text, file_updated, etc.
- **DB tables already exist in production** (stub migration `3270c24`)

### Backend — SSE Streaming (`services/api/app/routers/queries.py`)

`stream_query()` endpoint (POST `/projects/{project_id}/queries/stream`):
- Calls `run_agent_query()` which yields events
- Each event is JSON-serialized and sent as `data: {...}\n\n`
- On completion: saves query record, creates QueryPage records, tracks usage
- Current event types: text, thinking, tool_call, tool_result, code_execution, code_result, annotated_image, done, error

### Frontend — SSE Consumer (`apps/web/src/hooks/useQueryManager.ts`)

`processEvent()` handles: thinking, text, tool_call, tool_result, code_execution, code_result, annotated_image, done, error.
- Accumulates trace, selectedPages, annotatedImages
- Updates React state per event
- On `done`: extracts finalAnswer, findings, crossReferences from event data

### Frontend — Feed & Workspace (`apps/web/src/components/maestro/`)

**`FeedViewer.tsx`:** Renders feed items (user-query, pages, text, findings, annotated-images, workspace). Shows ThinkingSection during streaming.

**`PageWorkspace.tsx` + `WorkspacePageCard.tsx`:** Vertical scrollable page cards with:
- State badges (queued/processing/done)
- Pin/unpin toggle
- BBox overlays (raw + agent findings)
- Processing shimmer animation
- Already built and merged (commits `faab7aa`, `eb0d8e8`)

**`useWorkspacePages.ts`:** State management with:
- `addPage()`, `syncFromSelectedPages()`, `addBboxes()`, `setFindings()`
- `setPageState(pageId, state)` — queued/processing/done transitions
- `markAllDone()`, `togglePin()`, `clear()`

**`ThinkingSection.tsx`:** Processes trace into human-readable actions. Tool calls become "Searched for X → Found N", thinking becomes expandable text. Has timer.

**`MaestroMode.tsx`:** Top-level wiring. Uses useQueryManager + useWorkspacePages. Syncs workspace from selectedPages during streaming. Builds feedItems on query completion.

### Config & Feature Flags (`services/api/app/config.py`)

Current flags:
- `DEEP_MODE_V4_UNCONSTRAINED` (default True) — V4 agentic vision
- `DEEP_MODE_V3_AGENTIC` — V3 fallback
- `DEEP_MODE_VISION_V2` — V2 fallback
- `MED_MODE_REGIONS` — med mode toggle

### Environment

- **OS:** Windows 10 (development), Linux (Railway production)
- **Python:** 3.13
- **Node:** 22.x
- **Branch:** `feature/local-dev-setup`
- **Frontend:** `apps/web/` (Vite + React + TypeScript)
- **Backend:** `services/api/` (FastAPI + SQLAlchemy + asyncio)
- **DB:** PostgreSQL (local Docker for dev, Supabase for prod)
- **AI:** Gemini 3 Flash via google-genai SDK

---

## Requirements

### R1: Wire Big Maestro Models + Memory Into Codebase

**Files to modify:**
- `services/api/app/models/__init__.py` — add imports for `ProjectMemoryFile`, `LearningEvent`
- `services/api/app/schemas/query.py` — add `learning_mode: bool = False` field to `AgentQueryRequest`

**No migration needed** — tables already exist in production.

### R2: Build Maestro Orchestrator Entry Point

**New function:** `run_maestro_query()` in `big_maestro.py`

This replaces `run_with_learning()` as the main entry point. Flow:

```
run_maestro_query(db, project_id, user_id, query, history, viewing_context, mode)
│
├─ 1. Build memory context (build_memory_context)
├─ 2. Detect teaching intent
│   ├─ YES → process_learning() → yield learning events → return
│   └─ NO → continue
├─ 3. Run Fast Mode pipeline (reuse from run_agent_query_deep steps 1-7)
│   └─ yield: tool_call/tool_result events, page_state(queued) events
├─ 4. Spawn parallel per-page Deep agents (asyncio.gather)
│   ├─ For each page: call explore_with_agentic_vision_v4 with single page
│   ├─ yield: page_state(processing), thinking, code, annotated_image events per page
│   └─ As each completes: yield page_state(done), synthesize evolved response
├─ 5. Yield response_update events as each Deep agent completes
├─ 6. Final: yield done event with full trace, usage totals, evolved response
```

**Key detail:** The Fast Mode pipeline (steps 1-7 of current `run_agent_query_deep`) should be extracted into a reusable function, not duplicated. The orchestrator calls it, then fans out to parallel Deep agents.

### R3: Per-Page Deep Agent Function

**New function:** `run_deep_agent_for_page()` in `big_maestro.py` (or `agent.py`)

```python
async def run_deep_agent_for_page(
    page: dict,           # {page_id, page_name, image_bytes}
    search_mission: dict,  # per-page mission from build_search_missions
    query: str,
    memory_context: str,
    history_context: str,
    viewing_context: str,
) -> AsyncIterator[dict]:
    """
    Run Deep Mode V4 agentic vision on a single page.
    
    Yields:
      {"type": "thinking", "content": "...", "page_id": "..."}
      {"type": "code", "content": "...", "page_id": "..."}
      {"type": "annotated_image", "image_base64": "...", "page_id": "..."}
      {"type": "text", "content": "...", "page_id": "..."}
      {"type": "page_complete", "page_id": "...", "response_text": "...", "usage": {...}}
    """
```

This wraps `explore_with_agentic_vision_v4()` with a single-page list and the page's specific search mission. Tags all events with `page_id` so the frontend knows which page they belong to.

**Deep agents don't share findings.** Each runs independently. Same cost as current (one Gemini call per page × N pages vs one call with N pages — similar token count, but parallel execution).

### R4: Evolved Response Synthesis

After each Deep agent completes, the orchestrator synthesizes an updated response.

**Option A (simple, recommended for v1):** Concatenate per-page summaries with a template:
```python
def synthesize_evolved_response(page_results: list[dict]) -> str:
    """Build evolved response from completed page results."""
    parts = []
    for result in page_results:
        if result.get("response_text"):
            parts.append(f"**{result['page_name']}:** {result['response_text']}")
    return "\n\n".join(parts)
```

**Option B (future):** Use a lightweight Gemini call to synthesize findings into natural prose. Not for v1.

The evolved response is yielded as `response_update` SSE events.

### R5: New SSE Event Types

Add these to the backend event stream:

```python
# Page enters workspace
{"type": "page_state", "page_id": "...", "page_name": "...", "state": "queued"}
{"type": "page_state", "page_id": "...", "state": "processing"}
{"type": "page_state", "page_id": "...", "state": "done"}

# Evolved response updates (after each deep agent completes)
{"type": "response_update", "text": "...", "version": 1}

# Learning events (yellow aura in thinking section)
{"type": "learning", "text": "...", "classification": "routing", "file_updated": "..."}
```

The `queries.py` router passes these through like existing events — no special handling needed.

### R6: Wire Orchestrator Into Query Router

**Modify `services/api/app/routers/queries.py`:**

In `event_generator()`, when `learning_mode=True` OR behind a feature flag:
```python
if use_maestro_orchestrator:
    async for event in run_maestro_query(
        db, project_id, user.id, data.query,
        history_messages, viewing_context, data.mode
    ):
        yield f"data: {json.dumps(event)}\n\n"
else:
    # existing run_agent_query path (fallback)
    async for event in run_agent_query(...):
        yield f"data: {json.dumps(event)}\n\n"
```

**Feature flag:** `MAESTRO_ORCHESTRATOR` (default False for safe rollout, flip to True to enable).

### R7: Frontend — Handle New SSE Events

**Modify `apps/web/src/hooks/useQueryManager.ts` `processEvent()`:**

Add cases for:
- `page_state` → call workspace hook's `setPageState(pageId, state)` or `addPage()`
- `response_update` → store evolved response text, update UI
- `learning` → add to trace for thinking section display

**New accumulator fields:**
```typescript
evolvedResponse: string       // latest response_update text
evolvedResponseVersion: number // for ordering
```

### R8: Frontend — Evolved Response Component

**New component:** `EvolvedResponse.tsx`

A single prominent text block below the thinking section, above the input.
- Renders markdown (reuse existing ReactMarkdown setup)
- Updates in place as `response_update` events arrive
- Shows a subtle animation/transition when text updates
- "Still processing..." indicator when deep agents are still running

**Wire into `FeedViewer.tsx`** as a new feed item type or a persistent element during streaming.

### R9: Frontend — Thinking Section Enhancements

**Modify `ThinkingSection.tsx`:**

- Add visual treatment for `learning` events: yellow background/border class
- Handle `page_state` events in trace display: "📄 Found 4 relevant pages", "🔬 Processing E-3.2...", "✅ E-3.2 done"
- Timestamps on all entries (already has timer infrastructure)

**No click-to-restore.** Milestones are visual-only for now. No state snapshots.

### R10: Frontend — Wire Workspace to SSE Page States

**Modify `MaestroMode.tsx`:**

Currently workspace syncs from `selectedPages` on query completion. Change to:
- On `page_state(queued)` → `addPage({pageId, pageName, imageUrl, state: 'queued'})`
- On `page_state(processing)` → `setPageState(pageId, 'processing')`
- On `page_state(done)` → `setPageState(pageId, 'done')`

This gives real-time page state transitions during streaming instead of all-at-once on completion.

### R11: Memory Context Injection Into Prompts

**Modify `services/api/app/services/providers/gemini.py`:**

Add `{memory_section}` placeholder to:
- `DEEP_AGENTIC_VISION_V4_PROMPT` — so per-page Deep agents have project memory
- Fast mode prompt (in `route_fast_query` or `select_pages_smart`) — so page selection benefits from memory

**Modify orchestrator** to call `build_memory_context()` once and pass it to all agents.

---

## Constraints

1. **Feature flag everything.** `MAESTRO_ORCHESTRATOR` flag (default False). Existing flow untouched when flag is off.
2. **Don't modify existing `run_agent_query_deep()`** — it stays as fallback. New orchestrator is a separate code path.
3. **No schema migrations.** DB tables for memory already exist. No new tables needed.
4. **Branch only.** Work on `feature/local-dev-setup` (or child branch). Railway auto-deploys from `main` — do not merge.
5. **Don't break Fast/Med modes.** They continue to work unchanged. The orchestrator only affects deep mode flow.
6. **Parallel Deep agents are independent.** No finding-sharing between pages. Each gets its own search mission and runs to completion alone.
7. **Evolved response is simple concatenation for v1.** Don't add a synthesis Gemini call. Template-based assembly from per-page results.

---

## Implementation Order

1. **R1** — Wire models + schema (small, foundational)
2. **R2 + R3** — Orchestrator + per-page Deep agent (core backend, can test independently)
3. **R4** — Evolved response synthesis (simple, builds on R3 output)
4. **R5 + R6** — New SSE events + router wiring (connects backend to frontend)
5. **R7** — Frontend SSE handling (useQueryManager changes)
6. **R8** — Evolved response component (new UI)
7. **R9** — Thinking section enhancements (visual polish)
8. **R10** — Workspace ↔ SSE wiring (real-time page states)
9. **R11** — Memory context injection (enriches prompts with project knowledge)

Steps 1-6 are the critical path. Steps 7-10 are polish. Step 11 can happen any time after R1.

---

## Key Files Reference

### Backend (modify)
| File | What changes |
|------|-------------|
| `services/api/app/services/core/big_maestro.py` | Expand: add `run_maestro_query()`, `run_deep_agent_for_page()`, evolved response synthesis |
| `services/api/app/services/core/agent.py` | Extract Fast Mode pipeline into reusable function (don't duplicate) |
| `services/api/app/services/providers/gemini.py` | Add `{memory_section}` to V4 prompt |
| `services/api/app/routers/queries.py` | Add orchestrator dispatch path with feature flag |
| `services/api/app/schemas/query.py` | Add `learning_mode` field |
| `services/api/app/models/__init__.py` | Add ProjectMemoryFile, LearningEvent imports |
| `services/api/app/config.py` | Add `MAESTRO_ORCHESTRATOR` flag |

### Backend (read-only reference)
| File | Why |
|------|-----|
| `services/api/app/services/core/search_missions.py` | Per-page mission format — consumed by orchestrator |
| `services/api/app/services/memory.py` | Memory CRUD — called by orchestrator for context |

### Frontend (modify)
| File | What changes |
|------|-------------|
| `apps/web/src/hooks/useQueryManager.ts` | Handle page_state, response_update, learning events |
| `apps/web/src/components/maestro/FeedViewer.tsx` | Add evolved response rendering |
| `apps/web/src/components/maestro/ThinkingSection.tsx` | Yellow aura for learning, page state entries |
| `apps/web/src/components/maestro/MaestroMode.tsx` | Wire workspace to SSE page_state events |
| `apps/web/src/types/query.ts` | Add new event types to AgentTraceStep |

### Frontend (new)
| File | What |
|------|------|
| `apps/web/src/components/maestro/EvolvedResponse.tsx` | New component — live-updating response block |

---

## Testing Strategy

1. **Backend unit:** Run orchestrator with a test project, verify parallel Deep agents produce per-page events
2. **SSE verification:** Watch raw SSE stream in browser devtools — confirm page_state, response_update events appear
3. **Frontend visual:** Workspace cards should transition queued → processing → done in real-time
4. **Evolved response:** Should show partial text after first Deep agent, grow after each subsequent completion
5. **Fallback:** With `MAESTRO_ORCHESTRATOR=false`, existing deep mode should work identically
6. **Learning:** Send a teaching message with `learningMode=true`, verify memory file updated and yellow thinking events appear

---

*This document is the complete context for implementation. No other documents needed.*
