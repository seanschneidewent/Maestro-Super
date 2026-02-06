# Phase 3: The Learning Agent

## Context

Read `maestro/MAESTRO-ARCHITECTURE-V3.md` — it is the alignment doc for the entire V3 architecture. This phase adds the parallel Learning intelligence.

**Look at the Phase 1 and Phase 2 commits to understand what was built.** Phase 2 delivered:
- SessionManager with in-memory sessions + Supabase persistence
- New Maestro agent (persistent conversation, model-agnostic, tool-using)
- Provider abstraction for multi-model support
- V3 API routes (`/v3/sessions`, `/v3/sessions/{id}/query`)
- Experience injection (Maestro reads default + routed Experience every query)
- Frontend transformed: session-based workspace, new ThinkingSection with Workspace Assembly (cyan) panel
- Old agent system gutted

**Phase 2 left placeholders for Learning:**
- `LiveSession.learning_messages` exists but is empty
- `LiveSession.learning_queue` exists but nothing consumes it
- `InteractionPackage` is put on the queue after each Maestro turn but no worker processes it
- ThinkingSection has Learning (yellow) and Knowledge Update (purple) panel slots but they receive no events

## Goal

1. **Learning agent** — Persistent conversation that runs alongside Maestro, observing every interaction
2. **Experience filesystem tools** — Learning reads/writes/edits/creates Experience files autonomously
3. **Knowledge editing tools** — Learning can fix Pointer descriptions and trigger re-grounds
4. **Background worker** — Per-session Learning worker consuming the interaction queue at its own pace
5. **ThinkingSection panels** — Learning (yellow) and Knowledge Update (purple) panels live in the frontend

## What This Phase Delivers

After this phase ships:
- Every Maestro interaction gets packaged and fed to Learning asynchronously
- Learning observes the query, response, retrieved Pointers, Experience used, and workspace actions
- Learning autonomously writes to Experience: routing rules, corrections, preferences, schedule updates, new extended files
- Learning can fix Pointer descriptions directly (text corrections) or trigger re-ground for vision errors
- The ThinkingSection shows Learning's cognition in the yellow panel
- When Learning modifies Knowledge, the purple panel shows the surgical edit
- Experience gets richer with every interaction — Maestro gets smarter over time

## Architecture Reference

See the V3 alignment doc sections:
- **"Maestro Learning — The Benchmark Engine"** — full description of Learning's role and signals
- **"What Learning Observes"** — interaction packaging and signal types
- **"Learning's Tools"** — all tool definitions
- **"Code Expression: Learning Agent"** — `InteractionPackage`, tool schemas, `run_learning_turn()`, `run_learning_worker()`
- **"The Experience Filesystem"** — how Learning manages Experience, routing_rules.md as index
- **"Code Expression: Re-Ground"** — `trigger_reground()` function

## Gemini Re-Ground

When Learning triggers a re-ground, it spawns a Gemini agent to re-analyze a page region. This uses the same Gemini agentic vision as Brain Mode:
**https://ai.google.dev/gemini-api/docs/code-execution#python**

## Detailed Requirements

### R1: Interaction Packaging

**Create `services/api/app/types/learning.py`:**

```python
@dataclass
class InteractionPackage:
    user_query: str
    maestro_response: str
    pointers_retrieved: list[dict]          # [{pointer_id, title, description_snippet}]
    experience_context_used: list[str]      # paths of Experience files Maestro read
    workspace_actions: list[dict]           # [{action, page_ids/pointer_ids}]
    turn_number: int
    timestamp: float
```

**Verify Phase 2 creates this package correctly.** After each Maestro turn in `run_maestro_turn()`, an `InteractionPackage` should be created from the turn's data and put on `session.learning_queue`. If Phase 2 didn't implement this fully, complete it now.

### R2: Learning Agent

**Create `services/api/app/services/v3/learning_agent.py`:**

**System prompt** — defines Learning's identity:
- "You are the Learning agent for Maestro. You observe every interaction between Maestro and the superintendent."
- "Your job: evaluate the interaction, identify what can be learned, and write it to Experience or fix Knowledge."
- Instructions for each signal type (corrections, routing patterns, preferences, schedule info, gaps)
- Instructions for when to edit Knowledge directly vs trigger re-ground vs update Experience
- "When you create a new extended Experience file, ALWAYS update routing_rules.md with instructions for Maestro to find it"

**`run_learning_turn(session, interaction, db)`** → `AsyncIterator[dict]` (SSE events)

Flow:
1. Format `InteractionPackage` as a user message for Learning's conversation
2. Append to `session.learning_messages`
3. Build system prompt (Learning's identity + tool instructions)
4. Call `chat_completion(messages=learning_messages, tools=LEARNING_TOOLS, model=LEARNING_MODEL)`
5. Process tool calls:
   - Experience writes → execute, yield `ThinkingEvent(panel="learning")`
   - Knowledge edits → execute, yield `ThinkingEvent(panel="knowledge_update")`
   - Re-ground triggers → execute, yield `ThinkingEvent(panel="knowledge_update")`
6. Append assistant response to `session.learning_messages`
7. Mark `session.dirty = True`
8. Yield `LearningDoneEvent`

**Tool definitions** — 11 tools as specified in the V3 alignment doc:
```
Experience: read_file, write_file, edit_file, list_files
Knowledge read: read_pointer, read_page, search_knowledge
Knowledge write: edit_pointer, edit_page, update_cross_references
Re-ground: trigger_reground
```

### R3: Learning Tool Executor

**Create `services/api/app/services/v3/learning_tool_executor.py`:**

`execute_learning_tool(tool_name, tool_args, session, db)` → `dict`

**Experience filesystem tools:**
- `read_file(path)` → `SELECT content FROM experience_files WHERE project_id = ? AND path = ?`
- `write_file(path, content)` → `INSERT INTO experience_files (project_id, path, content, updated_by_session) VALUES (?, ?, ?, ?) ON CONFLICT (project_id, path) DO UPDATE SET content = ?, updated_by_session = ?, updated_at = now()`
- `edit_file(path, old_text, new_text)` → read file, replace old_text with new_text, write back. Error if old_text not found.
- `list_files()` → `SELECT path, updated_at FROM experience_files WHERE project_id = ?`

**Knowledge read tools:**
- `read_pointer(pointer_id)` → `SELECT title, description, cross_references, enrichment_metadata FROM pointers WHERE id = ?`
- `read_page(page_id)` → `SELECT page_name, sheet_reflection, cross_references, page_type FROM pages WHERE id = ?`
- `search_knowledge(query)` → same vector search as Maestro's `search_knowledge` tool

**Knowledge write tools:**
- `edit_pointer(pointer_id, field, new_content)` → update the specified field on the Pointer. Only `description` and `cross_references` are writable. After editing description, regenerate the embedding (call Voyage).
- `edit_page(page_id, field, new_content)` → update `sheet_reflection` or `cross_references` on the Page.
- `update_cross_references(pointer_id, references)` → update the `cross_references` JSONB field

**Re-ground tool:**
- `trigger_reground(page_id, instruction)` → calls `services/api/app/services/core/reground.py` (create this file)
  - Load page image from Supabase storage
  - Send to Gemini with instruction + existing Pointer bboxes for context
  - Gemini draws new/corrected bounding boxes (uses code execution — see https://ai.google.dev/gemini-api/docs/code-execution#python)
  - Create new Pointer rows with `enrichment_status='pending'`
  - Pass 2 worker (from Phase 1) automatically picks them up
  - Return list of new/updated pointer_ids

### R4: Learning Background Worker

**Add to `services/api/app/services/v3/learning_agent.py`:**

`run_learning_worker(session, db_factory)` — async function, one per session:
- Runs as asyncio background task, spawned when session is created
- Pulls from `session.learning_queue` (blocks when empty)
- For each `InteractionPackage`: calls `run_learning_turn(session, interaction, db)`
- Forwards SSE events to the session's event stream (so frontend receives them)
- Handles errors gracefully (log, continue processing next interaction)
- Stops when session is closed

**Integration with SessionManager:**
- When `create_session()` or `rehydrate_active_sessions()` creates a LiveSession, also spawn its Learning worker
- When `close_session()` is called, cancel the Learning worker task
- Store the `asyncio.Task` reference on the LiveSession for cleanup

### R5: SSE Event Forwarding

The Learning worker runs asynchronously — it may emit events while the user is idle or during their next query.

**Approach:** The session needs a mechanism to forward Learning events to connected SSE clients.

- Add an `event_bus: asyncio.Queue` to `LiveSession` that SSE connections listen to
- Learning worker puts events on this bus
- The SSE endpoint for `/query` yields events from both:
  1. The synchronous Maestro turn (immediate)
  2. Any pending Learning events from the event bus (streamed after Maestro, or interleaved)
- If no SSE connection is active when Learning emits events, they can be buffered or discarded (the Experience writes are persisted regardless)

### R6: Re-Ground Service

**Create `services/api/app/services/core/reground.py`:**

`trigger_reground(page_id, instruction, db)` → `list[str]` (pointer_ids)

1. Load page from DB (get `page_image_path`, existing Pointers with bboxes)
2. Download page image from Supabase storage
3. Build Gemini prompt:
   - "Re-analyze this construction drawing page"
   - Include the instruction from Learning (what's wrong, what to look for)
   - Include existing Pointer bboxes as context (so Gemini knows what was already found)
   - Ask Gemini to draw new/corrected bounding boxes using code execution
4. Parse Gemini output for new bboxes (same parsing as Pass 1)
5. Create new Pointer rows with `enrichment_status='pending'`
6. Return the new pointer_ids

Uses Gemini with code execution: https://ai.google.dev/gemini-api/docs/code-execution#python

### R7: Frontend — Learning ThinkingSection Panels

**Modify `apps/web/src/components/maestro/ThinkingSection.tsx`:**

The ThinkingSection was rebuilt in Phase 2 with the three-panel architecture. The Workspace Assembly (cyan) panel is already live. Now activate:

**Learning panel (yellow):**
- Receives `thinking` events with `panel === "learning"`
- Shows Learning's observations and Experience updates
- Appears after Maestro responds (async), animates in
- May still be processing when user sends next query — that's fine, it continues

**Knowledge Update panel (purple):**
- Receives `thinking` events with `panel === "knowledge_update"`
- Shows when Learning edits a Pointer description or triggers a re-ground
- Only appears when triggered (most turns won't have Knowledge updates)
- Shows: which Pointer was edited, what changed, or which page is being re-grounded

**SSE parsing:**
- Update the SSE event handler to route `thinking` events to the correct panel based on the `panel` field
- Handle `learning_done` event to mark Learning panel as complete

### R8: Config

**In `services/api/app/config.py`:**
- Set `LEARNING_MODEL` to a real value (recommendation: same as `MAESTRO_MODEL` initially, can be tuned later)
- Add `learning_model` setting

## Constraints

- **Do NOT modify Maestro agent behavior** — Phase 2 Maestro stays as-is. Learning is parallel, not in-line.
- **Learning is eventually consistent** — it runs at its own pace. Maestro never waits for Learning.
- **Experience concurrency** — Multiple Learning agents can write to the same Experience files. Use `ON CONFLICT DO UPDATE` for writes. Last-write-wins is acceptable for v1.
- **Re-ground is rare** — It only fires when Learning detects vision-level errors. Most corrections are text edits.
- **Keep it simple** — Learning v1 doesn't need to be perfect. It needs to work, observe, and write. Sophistication comes from the model and the system prompt, not complex code.

## File Map

```
NEW FILES:
  services/api/app/services/v3/learning_agent.py
  services/api/app/services/v3/learning_tool_executor.py
  services/api/app/services/core/reground.py
  services/api/app/types/learning.py

MODIFIED FILES:
  services/api/app/services/v3/session_manager.py    (spawn/cancel Learning workers)
  services/api/app/services/v3/maestro_agent.py       (verify InteractionPackage creation)
  services/api/app/types/session.py                   (add event_bus to LiveSession)
  services/api/app/config.py                          (set LEARNING_MODEL)
  services/api/app/routers/v3_sessions.py             (SSE forwarding from Learning)
  apps/web/src/components/maestro/ThinkingSection.tsx  (activate Learning + Knowledge Update panels)
  apps/web/src/hooks/useSession.ts                    (handle learning SSE events)
```

## Environment

- **OS:** Windows 10 (dev), Linux (Railway production)
- **Python:** 3.11+
- **Backend:** FastAPI + SQLAlchemy + Supabase (Postgres + pgvector)
- **Frontend:** React + TypeScript + Vite + TailwindCSS
- **Gemini docs:** https://ai.google.dev/gemini-api/docs/code-execution#python
- **Repo:** `C:\Users\Sean Schneidewent\Maestro-Super`
