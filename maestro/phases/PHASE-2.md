# Phase 2: The Stateful Shell (Maestro + Sessions)

## Context

Read `maestro/MAESTRO-ARCHITECTURE-V3.md` — it is the alignment doc for the entire V3 architecture. This phase implements the core product: the Maestro Shell.

**Look at the Phase 1 commit(s) to understand what was built.** Phase 1 created:
- `experience_files` and `sessions` tables in Supabase
- Pointer enrichment columns (`enrichment_status`, `cross_references`, `enrichment_metadata`)
- Pass 2 background worker enriching Pointers with rich markdown
- `ExperienceFile` and `MaestroSession` SQLAlchemy models
- Default Experience seeding on project creation
- Experience service at `services/api/app/services/v3/experience.py`

## Goal

1. **SessionManager** — In-memory session management with Supabase persistence. Sessions survive server restarts.
2. **New Maestro agent** — One clean agent file. Persistent conversation, model-agnostic, tool-using.
3. **Provider abstraction** — Multi-model support (Anthropic, OpenAI, Google, xAI) behind one interface.
4. **Workspace tools** — Maestro assembles and iterates the workspace through tool calls.
5. **Experience injection** — Maestro reads Experience every query. Routing rules guide extended file reads.
6. **V3 API routes** — New `/v3/sessions` endpoints replacing the old query system.
7. **Frontend transformation** — Modify the existing workspace to work with V3 sessions. Remove legacy ThinkingSection. Build new three-panel ThinkingSection (Workspace Assembly cyan panel only in this phase — Learning and Knowledge Update panels come in Phase 3).
8. **The Gut** — Remove old agent system (big_maestro.py, agent.py, fast/med/deep modes, conversation_memory.py, memory.py).

## What This Phase Delivers

After this phase ships:
- Superintendent opens the app → creates/resumes a workspace session
- Types a query → Maestro responds with full conversation context (not isolated Q&A)
- Maestro uses tools to search Knowledge, read Pointers, read Experience, assemble the workspace
- Workspace updates live (pages added/removed, Pointers highlighted) via SSE
- ThinkingSection shows Workspace Assembly cognition (cyan panel)
- Session persists across page refreshes and server restarts
- Model is configurable per instance via environment variable
- Old query system is gone

## Architecture Reference

See the V3 alignment doc sections:
- **"Code Expression: Core Python Types"** — `LiveSession`, `WorkspaceState` dataclasses
- **"Code Expression: Maestro Agent"** — tool definitions, `run_maestro_turn()`, `build_maestro_system_prompt()`
- **"Code Expression: Model Provider Abstraction"** — `chat_completion()` multi-provider router
- **"Code Expression: Experience Injection"** — `read_experience_for_query()` flow
- **"Code Expression: Session Manager"** — `SessionManager` class with all methods
- **"Code Expression: SSE Event Types"** — all events the frontend handles
- **"Code Expression: API Routes (V3)"** — new router endpoints
- **"Files to Remove"** — exact list of what gets gutted

## Detailed Requirements

### R1: Session Manager

**Create `services/api/app/services/v3/session_manager.py`:**

`SessionManager` class — singleton on the server process:

- `_sessions: dict[UUID, LiveSession]` — in-memory cache
- `create_session(project_id, user_id, session_type, workspace_name?, db)` → creates row in `sessions` table + `LiveSession` in memory
- `get_session(session_id, db)` → returns from memory, or rehydrates from Supabase if not cached
- `get_or_create_telegram_session(project_id, user_id, db)` → finds existing active telegram session or creates new
- `checkpoint_session(session, db)` → writes `maestro_messages`, `learning_messages`, `workspace_state` to Supabase
- `checkpoint_all_dirty(db)` → checkpoints all sessions where `dirty=True`
- `rehydrate_active_sessions(db)` → on startup, load all `status='active'` sessions into memory
- `close_session(session_id, db)` → final checkpoint, set `status='closed'`, remove from memory
- `reset_session(session_id, db)` → close old session, create new one (same project/user, fresh conversations)
- `compact_session(session, db)` → summarize older messages, keep recent verbatim

**Create `services/api/app/types/session.py`:**

`WorkspaceState` and `LiveSession` dataclasses as specified in the alignment doc. `LiveSession` holds:
- `session_id`, `project_id`, `user_id`, `session_type`
- `maestro_messages: list[dict]` — the live conversation
- `learning_messages: list[dict]` — the parallel Learning conversation (populated in Phase 3)
- `workspace_state: Optional[WorkspaceState]`
- `learning_queue: asyncio.Queue` — interactions waiting for Learning (used in Phase 3)
- `dirty: bool` — needs checkpoint
- `last_active: float`

**Background checkpoint loop:**
- Launch on server startup alongside Pass 2 worker
- Every 30 seconds, call `checkpoint_all_dirty()`

**Startup rehydration:**
- On server startup, call `rehydrate_active_sessions()` to restore sessions from Supabase

### R2: Model Provider Abstraction

**Create `services/api/app/services/v3/providers.py`:**

`chat_completion(messages, tools, model, stream=True)` → `AsyncIterator[dict]`

Routes based on model name prefix:
- `claude-*` → Anthropic API (existing key in config)
- `gpt-*` → OpenAI API
- `gemini-*` → Google AI API (existing key in config)
- `grok-*` → xAI API

Each provider adapter normalizes to a common streaming format:
```python
{"type": "token", "content": "..."}
{"type": "tool_call", "id": "...", "name": "...", "arguments": {...}}
{"type": "thinking", "content": "..."}
{"type": "done"}
```

Start with Anthropic (Claude) and Google (Gemini) since those API keys exist. OpenAI and xAI are stubbed — raise NotImplementedError with a clear message.

**Config:** `MAESTRO_MODEL` env var (default: `gemini-3-flash-preview`)

### R3: Maestro Agent

**Create `services/api/app/services/v3/maestro_agent.py`:**

This is the core of the shell. One file, clean.

**`run_maestro_turn(session, user_message, db)`** → `AsyncIterator[dict]` (SSE events)

Flow:
1. Append `{"role": "user", "content": user_message}` to `session.maestro_messages`
2. Read latest Experience via `read_experience_for_query(project_id, user_message, db)`
3. Build system prompt via `build_maestro_system_prompt(session_type, workspace_state, experience_context, project_name)`
4. Assemble messages: `[system_prompt] + session.maestro_messages`
5. Call `chat_completion(messages, tools, model=MAESTRO_MODEL, stream=True)`
6. Process streaming chunks:
   - Token → yield `TokenEvent`, accumulate response text
   - Tool call → execute tool, yield `ToolCallEvent` + `ToolResultEvent`, append tool results to messages, continue generation
   - Thinking → yield `ThinkingEvent(panel="workspace_assembly")`
7. Append complete assistant response to `session.maestro_messages`
8. Mark `session.dirty = True`
9. Package interaction into `InteractionPackage` and put on `session.learning_queue` (consumed in Phase 3)
10. Yield `DoneEvent`

**System prompt** — defines Maestro's identity:
- "You are Maestro, a construction plan analysis partner for superintendents"
- Gap awareness instructions ("be honest about what you're unsure of")
- Channel-aware context (workspace: "you can assemble pages on screen"; telegram: "you're texting with the super on the jobsite")
- Experience context injected into system prompt
- Tool descriptions

**Tools** — defined as function schemas:
- Workspace session: `search_knowledge`, `read_pointer`, `read_experience`, `list_experience`, `add_pages`, `remove_pages`, `highlight_pointers`, `pin_page`
- Telegram session: `search_knowledge`, `read_pointer`, `read_experience`, `list_experience`, `list_workspaces`, `workspace_action`

### R4: Tool Executor

**Create `services/api/app/services/v3/tool_executor.py`:**

`execute_maestro_tool(tool_name, tool_args, session, db)` → `dict`

Implementations:
- `search_knowledge(query, limit=10)` — use existing vector search infrastructure (`services/utils/search.py`). Search `pointers` table filtered to `session.project_id`. Return `[{pointer_id, title, description_snippet, page_name, page_id, confidence}]`
- `read_pointer(pointer_id)` — `SELECT title, description, cross_references FROM pointers WHERE id = ?`
- `read_experience(path)` — `SELECT content FROM experience_files WHERE project_id = ? AND path = ?`
- `list_experience()` — `SELECT path, updated_at FROM experience_files WHERE project_id = ?`
- `add_pages(page_ids)` — add to `session.workspace_state.displayed_pages`, return page metadata
- `remove_pages(page_ids)` — remove from `session.workspace_state.displayed_pages`
- `highlight_pointers(pointer_ids)` — set `session.workspace_state.highlighted_pointers`
- `pin_page(page_id)` — add to `session.workspace_state.pinned_pages`

Workspace tools also emit `WorkspaceUpdateEvent` SSE events so the frontend updates in real time.

### R5: Experience Injection

**Extend `services/api/app/services/v3/experience.py`** (created in Phase 1):

`read_experience_for_query(project_id, user_query, db)` → `(context_string, paths_read)`

1. Read all default files: `SELECT path, content FROM experience_files WHERE project_id = ? AND path IN (default_paths)`
2. Parse `routing_rules.md` content for routing instructions
3. Simple keyword/pattern matching: check if `user_query` matches any routing rule keywords
4. For matched rules, read the corresponding extended files
5. Concatenate all content into a formatted context string with file headers
6. Return the context string + list of paths that were read (for Learning's observation)

### R6: V3 API Routes

**Create `services/api/app/routers/v3_sessions.py`:**

```
POST   /v3/sessions                          → create_session
GET    /v3/sessions?project_id=...            → list_sessions
GET    /v3/sessions/{session_id}              → get_session
DELETE /v3/sessions/{session_id}              → close_session
POST   /v3/sessions/{session_id}/reset        → reset_session
POST   /v3/sessions/{session_id}/compact      → compact_session
POST   /v3/sessions/{session_id}/query         → query (SSE stream)
GET    /v3/projects/{project_id}/experience   → list_experience
GET    /v3/projects/{project_id}/experience/{path} → read_experience
```

The `/query` endpoint:
- Accepts `{"message": "..."}` body
- Gets or creates the session via SessionManager
- Calls `run_maestro_turn(session, message, db)`
- Returns `StreamingResponse` with SSE events

**Mount in `main.py`** alongside existing routers.

### R7: Frontend — Existing Workspace Transformation

**This is critical: modify the existing workspace, don't build from scratch.**

**Modify `apps/web/src/components/maestro/MaestroMode.tsx`:**
- Replace the conversation-based query flow with session-based flow
- On mount: call `POST /v3/sessions` to create a workspace session (or resume existing)
- Hold `session_id` in state
- Query submission: `POST /v3/sessions/{session_id}/query` with SSE streaming
- Remove references to conversation history panel (becomes Workspaces panel in Phase 4)
- Remove Fast/Med/Deep mode badges and routing
- Remove mode toggle UI

**Modify `apps/web/src/hooks/useQueryManager.ts`:**
- Rewrite to work with V3 session-based SSE events
- Remove multi-query concurrency model (V3 is one conversation, sequential turns)
- Parse new SSE event types: `token`, `thinking`, `workspace_update`, `tool_call`, `tool_result`, `done`
- `workspace_update` events directly update the displayed pages / highlighted Pointers

**Modify `apps/web/src/components/maestro/PageWorkspace.tsx`:**
- Wire to session workspace state (displayed_pages, highlighted_pointers, pinned_pages)
- Pages come from workspace_update SSE events, not from query trace extraction
- Keep the existing PageWorkspace visual components (WorkspacePageCard, BboxOverlay, etc.)

**Remove `apps/web/src/components/maestro/EvolvedResponse.tsx`:**
- Replaced by the new response rendering (simple markdown streaming)

### R8: Frontend — New ThinkingSection

**Replace `apps/web/src/components/maestro/ThinkingSection.tsx` entirely:**

Build the new three-panel ThinkingSection architecture:

**Base component: `CognitionPanel`**
- Reusable collapsible dropdown panel
- Props: `title`, `color` (cyan/yellow/purple), `content`, `isActive`, `defaultExpanded`
- Collapsed: single line showing title + color indicator
- Expanded: scrollable content area with markdown rendering
- Same component, different color theme

**ThinkingSection component:**
- Renders up to 3 CognitionPanel instances:
  1. **Workspace Assembly** (cyan) — `panel === 'workspace_assembly'` events
  2. **Learning** (yellow) — `panel === 'learning'` events (Phase 3, placeholder for now)
  3. **Knowledge Update** (purple) — `panel === 'knowledge_update'` events (Phase 3, placeholder for now)
- Current turn: panels are expanded (Workspace Assembly active in this phase)
- Historical turns: all panels collapsed, expandable on tap

**Layout — Flipped Order (see V3 doc "Layout — Flipped Order"):**
```
  Maestro Response              ← nearest the workspace
  🔵 Workspace Assembly          ← cognition
  🟡 Learning                    ← cognition (placeholder)
  🟣 Knowledge Update            ← cognition (placeholder, only if triggered)
  "User's query text"           ← nearest the chat bar
```

The response renders ABOVE the cognition panels. The user's query renders BELOW. This is the opposite of typical chat layout — Maestro's response connects UP to the workspace it describes.

**Scrollable history:**
- Each turn is a group: Response + cognition panels + user query
- Current turn fully expanded
- Historical turns collapsed into compact blocks
- Newest at bottom, oldest scrolls up

### R9: Frontend — Remove Legacy Components

**Remove or gut these files:**
- `components/maestro/EvolvedResponse.tsx` — gone (orchestrator-specific)
- `components/maestro/ModeToggle.tsx` — gone (no more Fast/Med/Deep)
- `components/maestro/ReasoningTrace.tsx` — gone (replaced by CognitionPanel)
- `components/maestro/QueryHistoryPanel.tsx` — gone (replaced by Workspaces panel in Phase 4; for now, just remove)
- `components/maestro/ConversationIndicator.tsx` — gone (no more conversation model)
- `components/maestro/NewConversationButton.tsx` — repurposed or removed
- Old SSE event type definitions in `types/query.ts` — replace with V3 event types

**Remove or gut these hooks:**
- `hooks/useConversation.ts` — gone (V3 uses sessions, not conversations)
- Simplify `hooks/useQueryManager.ts` to a V3 session-based hook (or replace entirely with a new `hooks/useSession.ts`)

### R10: The Gut — Backend

**Remove these files (see V3 doc "Files to Remove"):**
```
services/api/app/services/core/big_maestro.py
services/api/app/services/core/agent.py
services/api/app/services/core/search_missions.py
services/api/app/services/core/query_vision.py
services/api/app/services/conversation_memory.py
services/api/app/services/memory.py
services/api/app/services/agent.py
services/api/app/routers/queries.py
services/api/app/schemas/query.py
services/api/app/schemas/search.py
services/api/app/schemas/tools.py
services/api/app/services/tools.py
```

**Remove from `config.py`:**
- `MAESTRO_ORCHESTRATOR`, `FAST_RANKER_V2`, `FAST_SELECTOR_RERANK`, `MED_MODE_REGIONS`, `DEEP_MODE_VISION_V2`, `DEEP_MODE_V3_AGENTIC`, `DEEP_MODE_V4_UNCONSTRAINED` flags and their settings equivalents

**Add to `config.py`:**
- `MAESTRO_MODEL` constant and setting (default: `gemini-3-flash-preview`)
- `LEARNING_MODEL` constant and setting (default: TBD, placeholder for Phase 3)

**Update `main.py`:**
- Remove `queries` router import and mount
- Add `v3_sessions` router import and mount
- Launch SessionManager on startup (rehydrate + checkpoint loop)

**Do NOT remove (mark as legacy but keep for data compatibility):**
- `models/query.py`, `models/query_page.py`, `models/project_memory.py` — the models stay, the tables stay, the data stays. Just remove the service layer and routes that use them.
- `models/conversation.py` — keep, conversations table has historical data

## Constraints

- **Do NOT modify Brain Mode Pass 1 or Pass 2 worker** — Phase 1 deliverables stay intact
- **Keep existing workspace visual components** (WorkspacePageCard, BboxOverlay, PageWorkspace layout) — modify their data sources, don't rebuild them
- **The `sessions` table was created in Phase 1** — use it, don't recreate it
- **Experience files were seeded in Phase 1** — Maestro can read them now
- **The gut happens in this phase** — old system goes away. No feature flag coexistence.

## File Map

```
NEW FILES:
  services/api/app/services/v3/session_manager.py
  services/api/app/services/v3/maestro_agent.py
  services/api/app/services/v3/providers.py
  services/api/app/services/v3/tool_executor.py
  services/api/app/types/session.py
  services/api/app/routers/v3_sessions.py
  apps/web/src/hooks/useSession.ts                    (or rewrite useQueryManager)
  apps/web/src/types/v3.ts                            (V3 SSE event types)

MODIFIED FILES:
  services/api/app/services/v3/experience.py           (add read_experience_for_query)
  services/api/app/config.py                           (add MAESTRO_MODEL, remove old flags)
  services/api/app/main.py                             (mount V3 router, launch SessionManager)
  services/api/app/models/__init__.py                  (if needed)
  apps/web/src/components/maestro/MaestroMode.tsx      (session-based flow)
  apps/web/src/components/maestro/ThinkingSection.tsx   (full rewrite → 3-panel)
  apps/web/src/components/maestro/PageWorkspace.tsx     (wire to session state)
  apps/web/src/components/maestro/index.ts             (update exports)
  apps/web/src/types/index.ts                          (update type exports)

REMOVED FILES:
  services/api/app/services/core/big_maestro.py
  services/api/app/services/core/agent.py
  services/api/app/services/core/search_missions.py
  services/api/app/services/core/query_vision.py
  services/api/app/services/conversation_memory.py
  services/api/app/services/memory.py
  services/api/app/services/agent.py
  services/api/app/routers/queries.py
  services/api/app/schemas/query.py
  services/api/app/schemas/search.py
  services/api/app/schemas/tools.py
  services/api/app/services/tools.py
  apps/web/src/components/maestro/EvolvedResponse.tsx
  apps/web/src/components/maestro/ReasoningTrace.tsx
  apps/web/src/components/maestro/ConversationIndicator.tsx
```

## Environment

- **OS:** Windows 10 (dev), Linux (Railway production)
- **Python:** 3.11+
- **Node:** 22+ (frontend)
- **Backend:** FastAPI + SQLAlchemy + Supabase (Postgres + pgvector)
- **Frontend:** React + TypeScript + Vite + TailwindCSS
- **Repo:** `C:\Users\Sean Schneidewent\Maestro-Super`
- **Backend path:** `services/api/`
- **Frontend path:** `apps/web/`
