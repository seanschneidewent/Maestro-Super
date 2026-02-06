# Maestro Architecture V3 — The Partner

*Design conversation — 2026-02-06, expanded 2026-02-07, fully specified 2026-02-08*
*Code expressions added — 2026-02-08 (alignment doc for coding agent)*
*Status: Active design, ready for implementation*
*Participants: Sean + Ember*
*Supersedes: Everything. V3 is a clean slate.*

---

## The Gut

V3 is not an evolution. It's a replacement.

The entire current Maestro Mode agent system gets gutted:
- `big_maestro.py` — regex-based learning, teaching detection, orchestrator → **gone**
- `agent.py` — fast/med/deep mode routing, tool-based query agent → **gone**
- The stateless query/response pattern (reconstruct history from DB each request) → **gone**
- `ProjectMemoryFile` with its 8 fixed categories and regex classification → **gone**
- `conversation_memory.py` reconstruction-based history → **gone**
- Fast/Med/Deep mode distinction → **gone** (there is just Maestro)

**What stays:**
- Brain Mode Pass 1 (perfect, don't touch it)
- Supabase (auth, storage, database)
- PDF processing, page splitting
- Frontend workspace components (WorkspacePageCard, BboxOverlay, PageWorkspace)
- SSE streaming infrastructure
- Deployment (Vercel + Railway)
- File tree navigation

We're swapping the garbage for the partner.

### Files to Remove

**Backend — exact paths under `services/api/app/`:**
```
services/core/big_maestro.py          — regex learning, teaching detection, orchestrator, run_maestro_query()
services/core/agent.py                — fast/med/deep mode routing, tool-based query agent
services/core/search_missions.py      — V3 agentic search mission builder (deep mode specific)
services/core/query_vision.py         — deep mode vision pipeline (V2/V3/V4 agentic vision at query time)
services/conversation_memory.py       — reconstruction-based history (stateless pattern)
services/memory.py                    — ProjectMemoryFile CRUD, regex classification, 8 fixed categories
services/agent.py                     — legacy agent (pre-big-maestro)
models/project_memory.py              — ProjectMemoryFile + LearningEvent models
models/query.py                       — Query model (stateless query/response pattern)
models/query_page.py                  — QueryPage join table
routers/queries.py                    — query endpoints (POST /query SSE, GET /queries, etc.)
schemas/query.py                      — AgentQueryRequest, QueryResponse schemas
schemas/search.py                     — search-related schemas (if only used by old agent)
services/tools.py                     — tool implementations for old agent (search_pages, select_pages, etc.)
schemas/tools.py                      — tool schemas for old agent
```

**Backend — keep but modify:**
```
config.py                             — remove MAESTRO_ORCHESTRATOR, FAST_RANKER_V2, DEEP_MODE_* flags
                                        add MAESTRO_MODEL, LEARNING_MODEL, PASS2_MODEL config
routers/__init__.py                   — remove queries router import
main.py                               — remove queries router mount
services/core/brain_mode_processor.py — keep Pass 1, add Pass 2 enrichment entry point
services/providers/gemini.py          — keep, add Pass 2 enrichment function
services/utils/search.py              — keep vector search, adapt for V3 Knowledge retrieval
```

**Database tables to deprecate (do NOT drop — mark as legacy):**
```
queries                               — stateless query/response records
query_pages                           — query-to-page join table
project_memory_files                  — 8 fixed categories regex system
learning_events                       — old learning event log
```

**Frontend — to gut (paths under `apps/web/`):**
```
Conversation history panel             — replaced by Workspaces panel
Fast/Med/Deep mode badges + routing    — gone (there is just Maestro)
Mode toggle UI                         — gone
Old ThinkingSection (single panel)     — replaced by three-panel ThinkingSection
```

---

## Core Philosophy

**Maestro is a partner, not an answer machine.**

- Understanding the project (Knowledge)
- Understanding the user (Experience)
- Knowing what it doesn't know (Gap Awareness)
- Getting better from every single interaction (The Benchmark)
- Helping the superintendent understand and orchestrate (Partnership)
- Reaching out when it matters, not just responding (The Proactive Flip)

Learning is the default state. Every interaction teaches Maestro something. Every response gets benchmarked and improved. The benchmark IS the product.

---

## The Filing System IS the Wiring

The architecture is defined by how data is stored and how it flows between agents. Three agents, two storage layers, one shared brain.

### Two Storage Layers

**Hot Layer — In-Memory Session State**
Context windows live in memory on the server for the duration of the session. Just like having a conversation. The server holds the message arrays and sends the full thing to the LLM each turn. No reconstruction from the database. No stateless request/response. The server IS the state.

- Maestro message array (the live conversation)
- Learning message array (the parallel conversation)
- Workspace state (what's on screen)

**Cold Layer — Persisted in Supabase**
Survives across sessions. This is what makes Maestro smarter over time.

- **Knowledge** — Pointers (rich markdown descriptions, bboxes, cropped images, embeddings, cross-references). All in Supabase rows.
- **Experience** — A filesystem of markdown files managed by Learning. Stored as rows in Supabase (`experience_files` table: project_id, path, content). To Learning it's a filesystem. To the database it's rows.

**The conversation is disposable. The brain is permanent.**

When a session ends, the context windows die. Experience carries everything forward. Next session, Maestro gets a fresh conversation but Experience makes it smart from turn one.

**Sessions are persisted for resilience.** Context windows live in memory for performance, but are checkpointed to Supabase so sessions survive server restarts. If Railway redeploys, sessions rehydrate from the last checkpoint and the user picks up right where they left off.

### Access Control — Who Reads and Writes What

```
              READS                      WRITES
Brain Mode    —                          Knowledge (upload + re-ground)
Maestro       Knowledge + Experience     —
Learning      Knowledge + Experience     Knowledge + Experience + re-ground trigger
```

Maestro never writes. It reads Knowledge, reads Experience, talks to the super. Clean separation — Maestro is the conversationalist, Learning is the librarian.

Brain Mode writes Knowledge at upload time (Pass 1 + Pass 2) and when Learning triggers a re-ground. It never touches Experience.

Learning sees everything. It writes to both stores. It's the only agent that writes to Experience, and it shares write access to Knowledge with Brain Mode.

### Code Expression: New Supabase Tables

```sql
-- ============================================================
-- EXPERIENCE FILES — Learning's filesystem stored as rows
-- ============================================================
CREATE TABLE experience_files (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    path            TEXT NOT NULL,          -- e.g. 'routing_rules.md', 'subs/concrete.md'
    content         TEXT NOT NULL DEFAULT '',
    updated_by_session UUID,               -- which session last wrote this
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(project_id, path)
);

CREATE INDEX idx_experience_files_project ON experience_files(project_id);

-- ============================================================
-- SESSIONS — Persistent session state for resilience
-- ============================================================
CREATE TABLE sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL,
    session_type    TEXT NOT NULL CHECK (session_type IN ('workspace', 'telegram')),

    -- Workspace identity (NULL for telegram sessions)
    workspace_id    UUID,
    workspace_name  TEXT,

    -- Conversation state (checkpointed from memory)
    maestro_messages    JSONB NOT NULL DEFAULT '[]'::jsonb,
    learning_messages   JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Workspace state (NULL for telegram sessions)
    workspace_state     JSONB DEFAULT '{
        "displayed_pages": [],
        "highlighted_pointers": [],
        "pinned_pages": []
    }'::jsonb,

    -- Lifecycle
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'idle', 'closed')),
    last_active_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_sessions_project ON sessions(project_id);
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_active ON sessions(status) WHERE status = 'active';
```

### Code Expression: Core Python Types

```python
# services/api/app/models/experience_file.py

class ExperienceFile(Base):
    __tablename__ = "experience_files"

    id: Mapped[UUID]             # PK
    project_id: Mapped[UUID]     # FK -> projects
    path: Mapped[str]            # 'routing_rules.md', 'subs/concrete.md'
    content: Mapped[str]         # markdown content
    updated_by_session: Mapped[Optional[UUID]]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


# services/api/app/models/session.py

class MaestroSession(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID]
    project_id: Mapped[UUID]
    user_id: Mapped[str]
    session_type: Mapped[str]           # 'workspace' | 'telegram'
    workspace_id: Mapped[Optional[UUID]]
    workspace_name: Mapped[Optional[str]]
    maestro_messages: Mapped[list]      # JSONB — the live conversation
    learning_messages: Mapped[list]     # JSONB — the parallel conversation
    workspace_state: Mapped[Optional[dict]]  # JSONB
    status: Mapped[str]                 # 'active' | 'idle' | 'closed'
    last_active_at: Mapped[datetime]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

```python
# services/api/app/types/session.py — In-memory session representation

from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID
import asyncio

@dataclass
class WorkspaceState:
    displayed_pages: list[str] = field(default_factory=list)      # page_ids
    highlighted_pointers: list[str] = field(default_factory=list)  # pointer_ids
    pinned_pages: list[str] = field(default_factory=list)          # page_ids

@dataclass
class LiveSession:
    """In-memory session. The hot layer."""
    session_id: UUID
    project_id: UUID
    user_id: str
    session_type: str                        # 'workspace' | 'telegram'

    # Conversation state — these ARE the context windows
    maestro_messages: list[dict]             # [{role, content, tool_calls?, ...}]
    learning_messages: list[dict]            # [{role, content, tool_calls?, ...}]

    # Workspace (None for telegram)
    workspace_state: Optional[WorkspaceState]

    # Learning queue — interactions waiting for Learning to process
    learning_queue: asyncio.Queue = field(default_factory=asyncio.Queue)

    # Metadata
    dirty: bool = False                      # needs checkpoint to Supabase
    last_active: float = 0.0                 # time.time()
```

---

## The Three Agents

### 1. Brain Mode (Gemini) — The Knowledge Builder

**When:** Upload time (and re-grounding when Learning demands it)
**Model:** Gemini (vision + code execution)
**Owns:** Knowledge — the structured understanding of the plans

Brain Mode is the heavy lifter. It reads construction drawings with agentic vision, draws bounding boxes, extracts every detail, and produces atomic Pointers. This is the hard task — live vision analysis of complex technical drawings. Gemini earns its cost here.

#### Two-Pass Upload Pipeline

**Pass 1 (exists — perfect, don't touch):**
Gemini looks at the full page with agentic vision. Identifies self-contained details — the walk-in cooler detail, the equipment schedule, the panel schedule, the general notes block. Each gets a bounding box and a cropped image. These are the Pointers. Also produces the sheet_reflection — the page-level understanding of how everything on that sheet relates.

Under 30 seconds per page. Already shipped and working.

**Pass 2 (new — background job):**
For each Pointer created by Pass 1, a dedicated enrichment agent goes deep into the cropped image. Reads every dimension, every note, every spec callout, every line item in the table, every cross-reference. Produces a rich markdown blob — the complete textual identity of that detail.

Pass 2 receives:
- **Cropped image** — the visual (from the Pointer's bbox)
- **Sheet reflection** — the full-page understanding from Pass 1 (context)
- **Page name + discipline** — basic identity

Pass 2 writes back to the Pointer row:
- **Rich markdown description** — the complete textual extraction
- **Cross-references** — references to other sheets/details found within this crop
- **Vector embedding** — generated from the markdown

Pass 2 is a background job. Pass 1 finishes a page, creates Pointers. Pass 2 picks them up from a queue. Each Pointer is processed independently — failures don't block other Pointers. Can be throttled, parallelized, retried.

**The super can start working before Pass 2 finishes.** Pass 1 completes, they see the page structure and Pointer bboxes immediately. Pass 2 enriches Pointers in the background. If they query before a Pointer is fully enriched, Maestro works with what's available — Pass 1 title + sheet_reflection. Not ideal but functional. As Pass 2 completes, the knowledge gets richer.

**Cost is front-loaded.** All vision analysis happens at upload. Everything downstream is text retrieval and synthesis.

```
PDF Upload
  → Page splitting (exists)
    → Pass 1: Gemini full-page vision (exists)
      → Pointers created with bboxes + cropped images
      → Sheet reflection written to page
        → Pass 2 queued: per-Pointer enrichment agent (new)
          → Rich markdown + cross-refs + embedding written back to Pointer
```

#### Code Expression: Pass 2 Enrichment Pipeline

```python
# services/api/app/services/core/pass2_enrichment.py

from dataclasses import dataclass

@dataclass
class EnrichmentInput:
    pointer_id: str
    cropped_image_bytes: bytes            # from Supabase storage via pointer.png_path
    sheet_reflection: str                 # from parent page.sheet_reflection
    page_name: str                        # e.g. "A2.01"
    discipline_name: str                  # e.g. "Architectural"
    pointer_title: str                    # Pass 1 basic title

@dataclass
class EnrichmentOutput:
    rich_description: str                 # complete markdown extraction
    cross_references: list[str]           # ["S-101", "E-201", "Detail 4/A3.01"]
    embedding: list[float]               # 1024-dim Voyage vector from rich_description


async def enrich_pointer(input: EnrichmentInput) -> EnrichmentOutput:
    """
    Single Pointer enrichment. Gemini reads the cropped image with
    sheet_reflection as context. Extracts everything: dimensions, notes,
    specs, line items, cross-references. Returns rich markdown + embedding.

    Model: Gemini (same as Brain Mode, vision + code execution)
    Thinking: high
    """
    ...


async def run_pass2_worker():
    """
    Background worker that polls for pending Pointers and enriches them.

    Lifecycle:
    1. On server startup, reset any 'processing' status back to 'pending'
       (handles Railway restart mid-enrichment)
    2. Poll loop: SELECT * FROM pointers WHERE enrichment_status = 'pending'
       ORDER BY created_at LIMIT batch_size
    3. For each Pointer:
       a. SET enrichment_status = 'processing'
       b. Download cropped image from Supabase storage
       c. Call enrich_pointer()
       d. Write rich_description, cross_references, embedding back to Pointer row
       e. SET enrichment_status = 'complete'
       f. On failure: SET enrichment_status = 'failed', log error
    4. Sleep if no pending Pointers, then poll again

    Concurrency: asyncio.gather() with max_concurrent (e.g., 3-5 parallel enrichments)
    Throttle: respect Gemini rate limits
    """
    ...
```

```python
# New columns on Pointer model (services/api/app/models/pointer.py)
# ADD to existing Pointer class:

    enrichment_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )  # 'pending' | 'processing' | 'complete' | 'failed'

    # rich_description lives in the existing 'description' column
    # Pass 1 writes a basic title/description
    # Pass 2 overwrites with the rich markdown extraction
    # The 'title' column keeps the short title from Pass 1

    # cross_references as structured data (not just text in description)
    cross_references: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
    )  # ["S-101", "E-201", "Detail 4/A3.01"]
```

#### Re-Grounding

When Learning detects that a Pointer's visual analysis was wrong (not a text error — the bbox is wrong, a region was missed, something was cut off), it triggers a re-ground. This spawns a Brain Mode agent (Gemini) to go back to the sheet image, draw new or corrected bounding boxes, and create/update Pointer records. Those new Pointers then get queued for Pass 2 enrichment.

Re-grounding is for vision-level fixes. Text-level fixes are done by Learning directly editing the Pointer's markdown.

#### Code Expression: Re-Ground

```python
# services/api/app/services/core/reground.py

async def trigger_reground(
    page_id: str,
    instruction: str,         # from Learning: "missed detail in bottom-right", "bbox for WIC-1 is too tight"
    db: Session,
) -> list[str]:
    """
    Spawns Brain Mode Gemini agent targeting a specific page.

    1. Load page image from Supabase storage
    2. Send to Gemini with instruction + existing Pointer bboxes for context
    3. Gemini draws new/corrected bounding boxes
    4. Create new Pointer rows (or update existing) with enrichment_status='pending'
    5. Pass 2 worker picks them up automatically

    Returns: list of new/updated pointer_ids
    """
    ...
```

---

### 2. Maestro (The Shell) — The Partner

**When:** Every user interaction (workspace, Telegram, or heartbeat)
**Model:** Swappable (Opus 4.5, GPT 5.2, Gemini 3 Pro, Grok 4.1 Fast — config switch)
**Owns:** The user experience — retrieval, synthesis, workspace, gap awareness

Maestro is what the superintendent talks to. One mind, one name, one personality. The shell defines who Maestro is. The model behind it is a commodity input.

**Maestro is a persistent conversation.** Not isolated query/response pairs — a running context window that builds up over the session. Each new query has full history from the conversation so far, just like talking to a person. The context window IS the working memory for that session.

**Every inference call reads the latest Knowledge and Experience.** If Learning updated a Pointer's markdown between Q2 and Q3, Q3 gets the updated version. If Learning wrote a new routing rule, the next query picks it up. The hot layer (conversation) is per-session, but the cold layer (Knowledge + Experience) is always current.

#### What Maestro Does

- Retrieves relevant Pointers from Knowledge based on the query
- Reads Experience — default files always, extended files when routing rules say so
- Assembles and iterates the workspace (adds/removes pages, highlights Pointers)
- Synthesizes responses grounded in atomic Pointers
- Connects information across pages and disciplines
- **Flags gaps** — what it's confident about, what it's unsure about, where to look for more
- Streams through the ThinkingSection (workspace) or texts (Telegram)

#### Maestro's Tools

**Knowledge tools:**
- `search_knowledge(query)` — semantic search, returns relevant Pointers
- `read_pointer(pointer_id)` — get the full markdown description

**Experience tools:**
- `read_experience(path)` — read an Experience file
- `list_experience()` — see what's available in Experience

**Workspace tools (workspace sessions only):**
- `add_pages(page_ids)` — add pages to the workspace
- `remove_pages(page_ids)` — remove pages from the workspace
- `highlight_pointers(pointer_ids)` — highlight specific Pointers on displayed pages
- `pin_page(page_id)` — pin a page as a persistent reference

**Workspace action tools (Telegram sessions only):**
- `list_workspaces()` — see which workspaces exist
- `workspace_action(workspace_id, action)` — take actions in a workspace remotely

Maestro never writes to Knowledge or Experience. It reads and talks.

#### Code Expression: Maestro Agent

```python
# services/api/app/services/v3/maestro_agent.py

# Tool definitions — passed to LLM as function schemas
MAESTRO_TOOLS_WORKSPACE = [
    {
        "name": "search_knowledge",
        "description": "Semantic search across all Pointers in this project. Returns ranked results with pointer_id, title, description snippet, page_name, confidence.",
        "parameters": {
            "query": {"type": "string", "description": "Natural language search query"},
            "limit": {"type": "integer", "description": "Max results (default 10)", "default": 10},
        },
    },
    {
        "name": "read_pointer",
        "description": "Read the full rich description of a specific Pointer.",
        "parameters": {
            "pointer_id": {"type": "string"},
        },
    },
    {
        "name": "read_experience",
        "description": "Read an Experience file by path.",
        "parameters": {
            "path": {"type": "string", "description": "e.g. 'routing_rules.md', 'walk_in_cooler.md'"},
        },
    },
    {
        "name": "list_experience",
        "description": "List all Experience files available for this project.",
        "parameters": {},
    },
    {
        "name": "add_pages",
        "description": "Add pages to the workspace display.",
        "parameters": {
            "page_ids": {"type": "array", "items": {"type": "string"}},
        },
    },
    {
        "name": "remove_pages",
        "description": "Remove pages from the workspace display.",
        "parameters": {
            "page_ids": {"type": "array", "items": {"type": "string"}},
        },
    },
    {
        "name": "highlight_pointers",
        "description": "Highlight specific Pointers on displayed pages.",
        "parameters": {
            "pointer_ids": {"type": "array", "items": {"type": "string"}},
        },
    },
    {
        "name": "pin_page",
        "description": "Pin a page as a persistent reference in the workspace.",
        "parameters": {
            "page_id": {"type": "string"},
        },
    },
]

# Telegram Maestro gets these INSTEAD of workspace tools:
MAESTRO_TOOLS_TELEGRAM = [
    # search_knowledge, read_pointer, read_experience, list_experience — same as above
    {
        "name": "list_workspaces",
        "description": "List all workspaces for this project.",
        "parameters": {},
    },
    {
        "name": "workspace_action",
        "description": "Perform an action in a specific workspace remotely.",
        "parameters": {
            "workspace_id": {"type": "string"},
            "action": {"type": "string", "description": "The action to perform"},
        },
    },
]


async def run_maestro_turn(
    session: "LiveSession",
    user_message: str,
    db: Session,
) -> AsyncIterator[dict]:
    """
    Execute one Maestro conversation turn.

    Flow:
    1. Append user message to session.maestro_messages
    2. Read latest Experience (default files + routing-matched extended files)
    3. Build system prompt (channel-aware: workspace vs telegram)
    4. Assemble context: system prompt + Experience + maestro_messages
    5. Call LLM with tools
    6. Process tool calls (search_knowledge, read_pointer, workspace actions)
    7. Stream response tokens + workspace events via SSE
    8. Append assistant response to session.maestro_messages
    9. Mark session dirty for checkpoint
    10. Package interaction → enqueue for Learning

    Yields SSE events:
        {"event": "token", "data": "..."}
        {"event": "thinking", "data": {"panel": "workspace_assembly", "content": "..."}}
        {"event": "workspace_update", "data": {"action": "add_pages", "page_ids": [...]}}
        {"event": "workspace_update", "data": {"action": "highlight_pointers", "pointer_ids": [...]}}
        {"event": "done", "data": {}}
    """
    ...


def build_maestro_system_prompt(
    session_type: str,              # 'workspace' | 'telegram'
    workspace_state: Optional[WorkspaceState],
    experience_context: str,        # concatenated default Experience files
    project_name: str,
) -> str:
    """
    Build the system prompt that defines who Maestro is.

    The shell. The personality. The gap awareness instructions.
    Channel-aware: workspace Maestro knows about pages and tools;
    Telegram Maestro knows about workspaces and mobile context.
    """
    ...
```

```python
# services/api/app/services/v3/tool_executor.py

async def execute_maestro_tool(
    tool_name: str,
    tool_args: dict,
    session: "LiveSession",
    db: Session,
) -> dict:
    """
    Execute a Maestro tool call and return the result.

    Tool implementations:
    - search_knowledge  → vector search on pointers table (existing search infra)
    - read_pointer      → SELECT description FROM pointers WHERE id = ?
    - read_experience   → SELECT content FROM experience_files WHERE project_id = ? AND path = ?
    - list_experience   → SELECT path FROM experience_files WHERE project_id = ?
    - add_pages         → update session.workspace_state.displayed_pages, emit SSE
    - remove_pages      → update session.workspace_state.displayed_pages, emit SSE
    - highlight_pointers→ update session.workspace_state.highlighted_pointers, emit SSE
    - pin_page          → update session.workspace_state.pinned_pages, emit SSE
    """
    ...
```

#### Workspace Is a Living Thing

Maestro doesn't just answer a question and display some pages. It builds and iterates the workspace across the conversation.

Turn 1: *"Show me the walk-in cooler details."* Maestro searches Knowledge, finds the relevant Pointers, assembles the workspace — three pages up, cooler Pointers highlighted.

Turn 2: *"What about the electrical for it?"* Maestro adds the E-series pages, highlights the panel Pointer that connects, keeps the cooler pages. Workspace grows.

Turn 3: *"That middle sheet isn't relevant, drop it."* Maestro removes it. Workspace tightens.

Every turn, Maestro can modify what's on screen based on the ongoing conversation. The workspace state is part of the session.

#### Channel Awareness

Maestro's identity shifts based on where it's running. Same brain, different system prompts, different tool sets.

**Workspace Maestro:** "You're in the Electrical workspace. Here's what's on screen. You have tools to assemble and iterate the workspace." Thinks in terms of pages, Pointers, highlights, the full UX.

**Telegram Maestro:** "You're on Telegram. The super is on the jobsite. You have access to these workspaces: [Electrical, Mechanical, Site Work]. You can do work in any of them remotely. Keep responses mobile-friendly." Thinks in terms of text messages, workspace actions at a distance, schedule updates.

#### The Shell Is the Product

The shell defines:
- System prompt (who Maestro is)
- Knowledge retrieval (find relevant Pointers, assemble context)
- Streaming UX (ThinkingSection, workspace, bboxes from Knowledge)
- Gap awareness (honest about uncertainty, points to specific places)
- Experience injection (learned behaviors shape every response)

**Model-agnostic by design.** The task at query time is text retrieval and synthesis from pre-built Knowledge — fundamentally simpler than the vision task. This means:
- Cheaper/faster models may perform well
- Model selection is a cost/speed/quality tradeoff
- Benchmarking across providers is trivial (same Knowledge, same Experience, swap model)
- "New brain in the same body" — the shell stays, the model swaps

#### Code Expression: Model Provider Abstraction

```python
# services/api/app/services/v3/providers.py

from typing import AsyncIterator

async def chat_completion(
    messages: list[dict],
    tools: list[dict],
    model: str,                  # from config: MAESTRO_MODEL env var
    stream: bool = True,
) -> AsyncIterator[dict]:
    """
    Unified chat completion interface. Routes to the correct provider
    based on model name prefix:

        'claude-*'   → Anthropic API
        'gpt-*'      → OpenAI API
        'gemini-*'   → Google AI API
        'grok-*'     → xAI API

    Returns streaming chunks with:
        {"type": "token", "content": "..."}
        {"type": "tool_call", "name": "...", "arguments": {...}}
        {"type": "thinking", "content": "..."}
        {"type": "done"}

    Config: MAESTRO_MODEL env var per instance (e.g., 'claude-opus-4-5')
    """
    ...
```

---

### 3. Maestro Learning — The Benchmark Engine

**When:** Every single interaction, async after Maestro responds
**Model:** TBD (needs to be capable of evaluation and synthesis)
**Owns:** Experience — the accumulated understanding that shapes Maestro's behavior

**Learning is a persistent conversation running alongside Maestro.** Every Maestro session gets its own Learning. They're born together, they observe the same scope. Learning's context window accumulates over the session. After each Maestro turn, the interaction data feeds into Learning's conversation. Learning thinks about it, writes updates, and its context window carries everything it's observed so far.

**Learning is eventually consistent.** It runs at its own pace, parallel to Maestro. If the user and Maestro go back and forth quickly, Learning chugs along processing interactions as they come. It might be processing Q2's data while Maestro is already answering Q4. That's fine — Experience updates land when Learning finishes each thought. Maestro always reads the latest Experience at query time, whatever's been written so far.

**Learning runs on Query 1.** The first query has signal: what the user chose to ask FIRST (priority signal), whether retrieval was complete, whether the workspace assembly made sense. Lighter than later queries but still valuable.

#### What Learning Observes

The server packages each interaction and feeds it to Learning:

- The super's query
- Which Pointers Maestro retrieved
- What Experience context Maestro used
- Maestro's response
- Workspace actions (pages added, removed, zoomed, pinned)

*Conversation signals:*
- User corrects Maestro → wrong answer (hard signal)
- User follows up on specific part → that's what mattered
- User rephrases same question → answer missed the mark
- User moves to new topic → answer was sufficient
- User teaches ("always check E-sheets for equipment") → routing rule

*Workspace signals:*
- User adds a page Maestro didn't provide → missed retrieval
- User removes a page Maestro added → irrelevant retrieval
- User clicks/zooms into specific Pointer area → that's what they care about
- User navigates to a page after Maestro flags a gap → exploring the gap (richest signal)
- User pins a page → important reference, keep it accessible

#### Learning's Tools

Learning is an intelligent agent with a filesystem and Knowledge access. It decides what to write and where — no regex, no predefined classification. The intelligence of filing IS the Learning agent.

**Experience filesystem tools:**
- `read_file(path)` — read any Experience file
- `write_file(path, content)` — create or overwrite a file
- `edit_file(path, old, new)` — surgical edits to existing files
- `list_files()` — see what exists in Experience

**Knowledge read tools:**
- `read_pointer(pointer_id)` — read a Pointer's current markdown
- `read_page(page_id)` — read page-level data (sheet reflection, etc.)
- `search_knowledge(query)` — find relevant Pointers

**Knowledge write tools:**
- `edit_pointer(pointer_id, field, new_content)` — direct text edits to Pointer descriptions
- `edit_page(page_id, field, new_content)` — page-level edits
- `update_cross_references(pointer_id, references)` — fix cross-reference links

**Re-ground tool:**
- `trigger_reground(page_id, instruction)` — spawns Brain Mode Gemini agent to draw new bboxes on the sheet; resulting Pointers get queued for Pass 2

Learning decides the right level:
- **Wrong text in Pointer → edit Knowledge directly.** "WIC-1 is item 449, not 410" → Learning reads the Pointer, finds the error, edits the markdown. Fast, no vision.
- **Wrong vision (bad bbox, missed region) → trigger re-ground.** "You missed the detail in the bottom right" → Learning spawns Gemini to go look at the sheet again.
- **Maestro retrieval issue, Knowledge is fine → update Experience.** "Always check E-sheets for equipment queries" → Learning writes to routing_rules.md.

#### Code Expression: Learning Agent

```python
# services/api/app/services/v3/learning_agent.py

@dataclass
class InteractionPackage:
    """What Learning receives after each Maestro turn."""
    user_query: str
    maestro_response: str
    pointers_retrieved: list[dict]        # [{pointer_id, title, description_snippet}]
    experience_context_used: list[str]    # paths of Experience files Maestro read
    workspace_actions: list[dict]         # [{action, page_ids/pointer_ids}]
    turn_number: int
    timestamp: float


LEARNING_TOOLS = [
    # Experience filesystem
    {
        "name": "read_file",
        "description": "Read an Experience file.",
        "parameters": {"path": {"type": "string"}},
    },
    {
        "name": "write_file",
        "description": "Create or overwrite an Experience file. Also update routing_rules.md if creating a new extended file.",
        "parameters": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
    },
    {
        "name": "edit_file",
        "description": "Surgical edit to an existing Experience file. Finds exact old text and replaces with new text.",
        "parameters": {
            "path": {"type": "string"},
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
        },
    },
    {
        "name": "list_files",
        "description": "List all Experience files for this project.",
        "parameters": {},
    },
    # Knowledge read
    {
        "name": "read_pointer",
        "description": "Read a Pointer's full description.",
        "parameters": {"pointer_id": {"type": "string"}},
    },
    {
        "name": "read_page",
        "description": "Read page-level data (sheet reflection, cross references).",
        "parameters": {"page_id": {"type": "string"}},
    },
    {
        "name": "search_knowledge",
        "description": "Semantic search across Pointers.",
        "parameters": {"query": {"type": "string"}},
    },
    # Knowledge write
    {
        "name": "edit_pointer",
        "description": "Edit a Pointer's description or cross_references. For text corrections only.",
        "parameters": {
            "pointer_id": {"type": "string"},
            "field": {"type": "string", "enum": ["description", "cross_references"]},
            "new_content": {"type": "string"},
        },
    },
    {
        "name": "edit_page",
        "description": "Edit page-level data.",
        "parameters": {
            "page_id": {"type": "string"},
            "field": {"type": "string", "enum": ["sheet_reflection", "cross_references"]},
            "new_content": {"type": "string"},
        },
    },
    # Re-ground
    {
        "name": "trigger_reground",
        "description": "Spawn Brain Mode to re-analyze a page region. Use ONLY for vision errors (wrong bbox, missed region). NOT for text corrections.",
        "parameters": {
            "page_id": {"type": "string"},
            "instruction": {"type": "string", "description": "What's wrong and what to look for"},
        },
    },
]


async def run_learning_turn(
    session: "LiveSession",
    interaction: InteractionPackage,
    db: Session,
) -> AsyncIterator[dict]:
    """
    Process one interaction through Learning.

    Flow:
    1. Format interaction as a user message for Learning's conversation
    2. Append to session.learning_messages
    3. Build system prompt (Learning's identity + instructions)
    4. Call LLM with tools
    5. Process tool calls (file writes, Knowledge edits, re-grounds)
    6. Append assistant response to session.learning_messages
    7. Mark session dirty for checkpoint

    Yields SSE events for ThinkingSection:
        {"event": "thinking", "data": {"panel": "learning", "content": "..."}}
        {"event": "thinking", "data": {"panel": "knowledge_update", "content": "..."}}
        {"event": "learning_done", "data": {}}
    """
    ...


async def run_learning_worker(session: "LiveSession", db: Session):
    """
    Background task per session. Pulls from session.learning_queue,
    calls run_learning_turn() for each interaction.

    Runs at its own pace — eventually consistent.
    If queue has items, processes them in order.
    If queue is empty, awaits next item.
    """
    while True:
        interaction = await session.learning_queue.get()
        async for event in run_learning_turn(session, interaction, db):
            # Forward SSE events to the session's event stream
            ...
```

#### The Experience Filesystem

Experience is a filesystem of markdown files managed by Learning. It's stored in Supabase (`experience_files` table: project_id, path, content) but to Learning it behaves like a filesystem.

**Default files (Maestro reads these every query):**
```
Experience/
├── routing_rules.md    (query routing patterns + index to extended files)
├── corrections.md      (truth corrections from user)
├── preferences.md      (user behavior patterns)
├── schedule.md         (current project schedule — from conversations)
└── gaps.md             (tracked gaps and their status)
```

**Extended files (Learning creates as needed):**
Learning can create any files the project needs:
```
Experience/
├── routing_rules.md
├── corrections.md
├── preferences.md
├── schedule.md
├── gaps.md
├── walk_in_cooler.md          ← deep thread emerged
├── subs/
│   ├── concrete.md            ← concrete sub details
│   └── electrical.md          ← electrical sub details
├── daily_notes/
│   ├── 2026-02-10.md          ← what happened Monday
│   └── 2026-02-11.md          ← what happened Tuesday
└── routing/
    ├── electrical.md          ← complex enough to split
    └── mechanical.md
```

**routing_rules.md is the index to the whole system.** When Learning creates an extended file, it also updates routing_rules.md with instructions for Maestro: "when the user asks about walk-in coolers, WIC-1, or cooler equipment, also read `walk_in_cooler.md`." Learning is literally training Maestro's retrieval in real time.

Maestro always reads the default files. When it sees routing instructions pointing to extended files that match the query, it pulls those too. Learning set Maestro up for that moment turns or days ago.

**Learning's quality directly determines Maestro's quality.** Bad filing → Maestro misses context. Good filing → Maestro feels like it's known this project forever.

Example `routing_rules.md`:
```markdown
# Routing Rules

## Default Routes
- Equipment queries → check Pointer cross-references to E-series pages
- Dimension queries → include detail sheets + plan views for cross-verification

## Extended Knowledge
- Walk-in cooler / WIC-1 / cooler equipment → read `walk_in_cooler.md`
- Concrete sub / ABC Concrete / pour schedule → read `subs/concrete.md`
- Electrical routing (complex) → read `routing/electrical.md`

## Learned Patterns
- Super always wants dimensions first, then specs
- When discussing equipment, always include panel schedule connections
```

Example `schedule.md`:
```markdown
# Project Schedule (last updated via Telegram 2/11)

## Active
- Excavation: building addition footings (started 2/10)
- Concrete: canopy footings pour scheduled Friday 2/14, 6am

## Coming Up
- Rebar inspection needed before canopy pour
- Vapor barrier crew: NOT YET SCHEDULED (need before slab pour)

## Notes from Super
- "Doing everything in one pour" (changed from two-stage, 2/11)
- Concrete sub: ABC Concrete
```

#### Code Expression: Experience Injection

```python
# services/api/app/services/v3/experience.py

DEFAULT_EXPERIENCE_PATHS = [
    "routing_rules.md",
    "corrections.md",
    "preferences.md",
    "schedule.md",
    "gaps.md",
]


async def read_experience_for_query(
    project_id: str,
    user_query: str,
    db: Session,
) -> tuple[str, list[str]]:
    """
    Build the Experience context that Maestro receives each query.

    1. Read all default files (always)
    2. Parse routing_rules.md for routing instructions
    3. Match user_query against routing rules (keyword/pattern match)
    4. Read any matched extended files
    5. Concatenate into a single context string

    Returns:
        (experience_context_string, list_of_paths_read)
    """
    ...


async def seed_default_experience(project_id: str, db: Session):
    """
    Called when a project is created. Seeds empty default Experience files
    so Learning and Maestro have a starting structure.

    Creates: routing_rules.md, corrections.md, preferences.md, schedule.md, gaps.md
    with minimal starter content/headers.
    """
    ...
```

---

## Session Management — Stateful Server

The server goes from completely stateless to stateful. This is a fundamental infrastructure shift.

### Session Architecture

Every Maestro session has a paired Learning session. They're born together when a session starts.

```
Project
├── Knowledge (shared, Supabase)
├── Experience (shared filesystem, Supabase)
│
├── Workspace: "Electrical"
│   ├── Maestro (conversation + workspace state)
│   └── Learning (conversation, writes shared Experience)
│
├── Workspace: "Mechanical"
│   ├── Maestro (conversation + workspace state)
│   └── Learning (conversation, writes shared Experience)
│
├── Telegram
│   ├── Maestro (conversation + heartbeat)
│   └── Learning (conversation, writes shared Experience)
```

Multiple Learning agents, one Experience. Multiple Maestro agents, one Knowledge. The shared layers are what make the whole thing feel like one mind.

### Workspace Session

```
WorkspaceSession
├── session_id
├── workspace_id
├── project_id
├── user_id
├── maestro_messages[]           ← the live conversation (growing message array)
├── workspace_state
│   ├── displayed_pages[]        ← which pages are showing
│   ├── highlighted_pointers[]   ← which Pointers are active
│   └── pinned_pages[]           ← pages the super pinned
├── learning_messages[]          ← parallel Learning conversation
├── created_at
├── last_active_at
```

### Query Flow (Workspace)

1. Super sends a query
2. Append their message to `maestro_messages`
3. Pull relevant Pointers from Knowledge (semantic search + routing rules)
4. Read latest Experience (default files + routed extended files)
5. Send the **full** `maestro_messages` array + Pointer context + Experience to the LLM
6. Stream Maestro's response, append it to `maestro_messages`
7. Maestro's workspace tool calls update `workspace_state` → frontend gets events via SSE
8. Async: package the interaction, feed to `learning_messages`, Learning processes at its own pace

### Telegram Session

Same structure minus workspace_state. The Telegram session is long-lived — it persists across workspace sessions. The super texts Maestro for days from the field. Workspaces come and go.

Telegram Maestro knows which workspaces exist and can target them remotely. "Go into my electrical workspace and pull up the panel details" → Maestro does the work in that workspace, tells the super to come look.

### Session Lifecycle

**Workspace:** Super opens workspace → session created (fresh Maestro + Learning conversations). Super is active → session alive. Super closes workspace or walks away → session sits idle → eventually cleaned up. Experience already persisted. Next time → fresh session, but Experience makes Maestro smart from turn one.

**Telegram:** Long-lived. The super controls it with two bot menu commands:
- **Reset** — fresh conversation, same brain. Knowledge + Experience persist. Same as creating a new workspace.
- **Compact** — compress the conversation. Summarize older turns, free up context space, keep the thread alive.

### Concurrency Model

Maestro is synchronous with the user (request → response). Learning is a background worker attached to the session, processing a queue of interactions at its own pace.

If the super sends Q2 while Learning is still processing Q1, that's fine. Learning processes its queue in order. Maestro reads whatever Experience has been written so far on each query.

### Code Expression: Session Manager

```python
# services/api/app/services/v3/session_manager.py

class SessionManager:
    """
    Manages the hot layer. Singleton on the server process.

    In-memory dict of LiveSession objects, backed by Supabase for persistence.
    """

    def __init__(self):
        self._sessions: dict[UUID, LiveSession] = {}
        self._checkpoint_interval: float = 30.0  # seconds between checkpoints

    async def create_session(
        self,
        project_id: UUID,
        user_id: str,
        session_type: str,           # 'workspace' | 'telegram'
        workspace_name: Optional[str] = None,
        db: Session = None,
    ) -> LiveSession:
        """
        Create a new session.

        1. Create row in sessions table (cold layer)
        2. Create LiveSession in memory (hot layer)
        3. Spawn Learning background worker for this session
        4. Return LiveSession
        """
        ...

    async def get_session(self, session_id: UUID, db: Session = None) -> Optional[LiveSession]:
        """
        Get session from memory, or rehydrate from Supabase if not in memory.
        Returns None if session doesn't exist or is closed.
        """
        ...

    async def get_or_create_telegram_session(
        self, project_id: UUID, user_id: str, db: Session = None,
    ) -> LiveSession:
        """
        Telegram sessions are long-lived. Find existing active telegram session
        for this user+project, or create a new one.
        """
        ...

    async def checkpoint_session(self, session: LiveSession, db: Session):
        """
        Write hot layer to cold layer.

        UPDATE sessions SET
            maestro_messages = ?,
            learning_messages = ?,
            workspace_state = ?,
            last_active_at = now(),
            updated_at = now()
        WHERE id = ?
        """
        ...

    async def checkpoint_all_dirty(self, db: Session):
        """
        Called periodically (every checkpoint_interval seconds).
        Checkpoints all sessions with dirty=True.
        """
        ...

    async def rehydrate_active_sessions(self, db: Session):
        """
        Called on server startup.
        Load all sessions with status='active' from Supabase into memory.
        Spawn Learning workers for each.
        """
        ...

    async def close_session(self, session_id: UUID, db: Session):
        """
        Close a session. Final checkpoint, then remove from memory.
        Sets status='closed' in Supabase. Experience already persisted.
        """
        ...

    async def reset_session(self, session_id: UUID, db: Session) -> LiveSession:
        """
        Telegram reset. Close old session, create new one.
        Same project, same user, fresh conversations.
        Knowledge + Experience untouched.
        """
        ...

    async def compact_session(self, session: LiveSession, db: Session):
        """
        Telegram compact. Summarize older messages, free context space.
        Keep recent turns verbatim, compress older ones into a summary message.
        """
        ...
```

```python
# services/api/app/services/v3/checkpoint.py — Background checkpoint loop

async def run_checkpoint_loop(manager: SessionManager, db_factory):
    """
    Runs as asyncio background task on server startup.
    Every 30 seconds, checkpoint all dirty sessions to Supabase.
    """
    while True:
        await asyncio.sleep(manager._checkpoint_interval)
        async with db_factory() as db:
            await manager.checkpoint_all_dirty(db)
```

---

## Heartbeat System — The Proactive Flip

The heartbeat is where Maestro stops being reactive and starts being a partner. Maestro thinks about the project on its own and reaches out via Telegram when it has something worth saying.

**The heartbeat runs through Telegram Maestro.** Not a separate session. Same Telegram conversation, same context window. A scheduled trigger fires and Maestro takes its own turn — same tools, same Knowledge, same Experience. The heartbeat is just another Maestro conversation turn where Maestro initiates instead of the super.

Because it's the same Telegram conversation, Maestro has full context. It remembers the super said "concrete guys moved to Thursday" three hours ago. It knows it asked about the vapor barrier crew yesterday. The heartbeat isn't a cold start — it's a continuation.

### Three Data Inputs

The heartbeat cross-references three layers:

1. **Knowledge** (the plans) — every Pointer, every cross-reference, every detail
2. **Schedule** (from Experience) — what phase is active, what's coming next, trade sequencing
3. **Experience** (accumulated learning) — what the super cares about, correction history, behavioral patterns

### The Schedule Lives in the Super's Head

Maestro doesn't pretend to know the schedule. The superintendent IS the schedule — they hold the trade sequencing, the changes, the phone calls with subs, the weather delays. Maestro helps them externalize it through conversation, then cross-references it against the plans.

Schedule storage is simple: `schedule.md` in Experience. Maestro reads it. Learning writes it when the super shares scheduling info. No external scheduling software. Google Calendar integration deferred — bolts on as a nicer input source when ready.

### Two Types of Heartbeat: Telling and Asking

**Telling — proactive reminders and insights:**
- *"Canopy footing pour today. Before you close the forms — the structural detail shows 6 anchor bolts but the equipment schedule only calls out 4 attachment points. Worth verifying before the concrete covers them."*
- *"Remember to take photos of the concrete guys using the vibrator while they're pouring the canopy footings."*

**Asking — drawing out the schedule through calculated questions:**

This is the partnership at its deepest. Maestro looks at what it knows from the plans (Knowledge), what it's learned so far (Experience), and identifies what it DOESN'T know about the schedule — then asks the question that fills the gap.

- *"Once the addition footings are poured, are you going right into the slab or do the walls go up first?"*
- *"The mechanical pad for the RTU on the north side — same concrete mobilization as the addition footings, or separate pour?"*
- *"I see fire-rated wall assemblies on the addition detail. Is your framing crew handling that or is that a specialty sub?"*
- *"The equipment schedule shows a lead time note on the walk-in cooler compressor. Have you confirmed delivery timing with the mechanical sub?"*

Every question is grounded in Knowledge (the plans), shaped by Experience (what Maestro has learned), and aimed at the gap. The super's answer fills the gap AND teaches Maestro something new.

### The Flywheel

Better Knowledge × Better Experience → Smarter questions → Richer answers → Better Experience → Even smarter questions.

Each answer opens the next question. Maestro discovers sequencing by asking about it. The super says "walls first, then slab — we're doing tilt-up panels." Now Maestro asks about the tilt-up sub's schedule, cross-references structural details for panel connections, flags that conduit stubs need to be in place before the slab pour.

**Blood and Electricity.** Two intelligences — one knows the plans cold, one knows the jobsite cold. Neither has the full picture alone. Together they hold the whole project.

### The Heartbeat Data Loop

1. **Read** — schedule.md + daily notes + Knowledge + Experience
2. **Cross-reference** — what's active today against the plans (Knowledge Pointers)
3. **Generate** — proactive insight or calculated scheduling question
4. **Send** — via Telegram
5. **Learn** — from the super's response → Learning updates Experience

---

## The Pointer — Atomic Unit of Knowledge

Pointers are the bridge between Knowledge and the Shell. Every model candidate gets the same structured input.

**Pointer in Supabase:**
```
Pointer (row in pointers table)
├── id (unique)
├── page_id (which sheet)
├── title (AI-generated, descriptive)
├── description (rich markdown — the complete textual identity of this detail)
├── bbox (normalized coordinates on the page)
├── cross_references[] (links to related Pointers on other pages)
├── vector_embedding (for semantic search, generated from description)
├── cropped_image_path (PNG of this region in Supabase storage)
├── enrichment_status (pending | processing | complete | failed)
├── metadata
│   ├── confidence
│   ├── last_updated
│   └── reground_count
└── timestamps (created_at, updated_at)
```

**Pass 1 creates:** id, page_id, title (basic), bbox, cropped_image_path, enrichment_status=pending
**Pass 2 enriches:** description (rich markdown), cross_references, vector_embedding, enrichment_status=complete
**Learning can edit:** description, cross_references, metadata (direct text corrections)
**Re-ground recreates:** new bbox, new crop → queued for Pass 2

The Page becomes a container:
```
Page (row in pages table)
├── id
├── discipline_id
├── page_name
├── file_path (PDF/image in Supabase storage)
├── page_image_path (rendered PNG)
├── sheet_reflection (Pass 1 output — page-level understanding)
├── page_type (detail_sheet, plan, schedule, etc.)
├── cross_references (sheet-level references from Pass 1)
├── pointers[] (relationship — the atomic Knowledge lives here)
└── timestamps
```

All the intelligence lives at the Pointer level. The Page holds the image and the sheet_reflection (which gives context to the Pointers). When Maestro retrieves context for a query, it's pulling Pointer markdown descriptions, not page-level blobs.

### Code Expression: Pointer Schema Changes

```python
# Changes to existing services/api/app/models/pointer.py
# ADD these columns to the existing Pointer class:

    # Enrichment status — tracks Pass 2 pipeline progress
    enrichment_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        index=True,                # indexed for Pass 2 worker polling
    )  # 'pending' | 'processing' | 'complete' | 'failed'

    # Structured cross-references (Pass 2 extracts these)
    cross_references: Mapped[Optional[list]] = mapped_column(
        JSONB,
        nullable=True,
    )  # ["S-101", "E-201", "Detail 4/A3.01"]

    # Metadata for benchmarking and re-ground tracking
    enrichment_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )  # {"confidence": 0.95, "reground_count": 0, "last_enriched_at": "..."}

# REMOVE (redundant with enrichment_status):
#   needs_embedding — replaced by enrichment_status != 'complete'

# KEEP existing columns:
#   id, page_id, title, description, bbox_x/y/width/height, png_path,
#   embedding, text_spans, ocr_data (legacy), created_at, updated_at
```

```sql
-- Alembic migration for Pointer enrichment columns
ALTER TABLE pointers ADD COLUMN enrichment_status VARCHAR(20) NOT NULL DEFAULT 'pending';
ALTER TABLE pointers ADD COLUMN cross_references JSONB;
ALTER TABLE pointers ADD COLUMN enrichment_metadata JSONB;
CREATE INDEX idx_pointers_enrichment_status ON pointers(enrichment_status);

-- Set existing enriched pointers to 'complete' (they already have descriptions)
UPDATE pointers SET enrichment_status = 'complete'
WHERE description IS NOT NULL AND description != '' AND embedding IS NOT NULL;

-- Set others to 'pending' for re-enrichment
UPDATE pointers SET enrichment_status = 'pending'
WHERE enrichment_status != 'complete';
```

---

## ThinkingSection Architecture

The ThinkingSection shows three distinct cognition panels — equally styled standalone dropdown components that reveal the underlying reasoning of each agent.

### The Three Panels

**1. Workspace Assembly (Cyan)**
Shows Maestro's retrieval and synthesis cognition — which Pointers it found, how it assembled the workspace, what connections it made, what gaps it flagged. This is the Shell thinking out loud.

**2. Learning (Yellow)**
Shows the Learning agent's observation and evaluation — what signals it detected, what Experience updates it's writing, what benchmark criteria emerged. Appears after Maestro responds (async), then persists. May still be processing when the user sends their next query — that's fine, it finishes at its own pace.

**3. Knowledge Update (Purple)**
Shows the surgical Knowledge fixer — Learning editing a Pointer directly or the spawned Gemini agent re-analyzing a region. Only appears when Learning modifies Knowledge. Rare, but visible when it happens.

### Styling

All three panels are the same component with a color theme swap. Each is a standalone collapsible dropdown. Collapsed by default for historical turns, expandable to audit the cognition on any past turn.

### Layout — Flipped Order

The response lives closest to the workspace. The query lives closest to the chat bar. Cognition sits in between.

```
┌─────────────────────────────────────────┐
│           WORKSPACE                      │
│    (pages, bboxes, highlights)           │
└─────────────────────────────────────────┘

  Maestro Response              ← nearest the workspace it describes
  🔵 Workspace Assembly          ← cognition (collapsible)
  🟡 Learning                    ← cognition (collapsible)
  🟣 Knowledge Update            ← cognition (collapsible, if triggered)
  "User's query text"           ← nearest the chat bar

┌─────────────────────────────────────────┐
│  Ask about your plans...          [Send] │
└─────────────────────────────────────────┘
```

**Spatial logic:** Maestro's response connects UP to the workspace it's referencing. The user's query connects DOWN to the input where they typed it. Cognition is the reasoning bridge between question and answer, available but not in the way.

### Scrollable History

The current query turn is fully expanded. All historical turns are collapsed above it, scrollable. Each historical turn is a group: Maestro Response + cognition panels + user query, all collapsed into a compact block. Tap any historical turn to expand and audit its cognition.

Standard chat scroll — newest at bottom, oldest scrolls up.

### Code Expression: SSE Event Types

```python
# services/api/app/services/v3/sse_events.py

from typing import Literal, Optional

# All SSE events emitted during a Maestro turn

@dataclass
class TokenEvent:
    event: Literal["token"] = "token"
    content: str = ""

@dataclass
class ThinkingEvent:
    event: Literal["thinking"] = "thinking"
    panel: str = ""          # 'workspace_assembly' | 'learning' | 'knowledge_update'
    content: str = ""

@dataclass
class WorkspaceUpdateEvent:
    event: Literal["workspace_update"] = "workspace_update"
    action: str = ""         # 'add_pages' | 'remove_pages' | 'highlight_pointers' | 'pin_page'
    page_ids: list[str] = field(default_factory=list)
    pointer_ids: list[str] = field(default_factory=list)

@dataclass
class ToolCallEvent:
    event: Literal["tool_call"] = "tool_call"
    tool: str = ""
    arguments: dict = field(default_factory=dict)

@dataclass
class ToolResultEvent:
    event: Literal["tool_result"] = "tool_result"
    tool: str = ""
    result: dict = field(default_factory=dict)

@dataclass
class LearningDoneEvent:
    event: Literal["learning_done"] = "learning_done"

@dataclass
class DoneEvent:
    event: Literal["done"] = "done"

# Frontend SSE handler maps:
#   "token"             → append to response text
#   "thinking"          → route to correct ThinkingSection panel by panel field
#   "workspace_update"  → update workspace state (add/remove pages, highlight pointers)
#   "tool_call"         → show in Workspace Assembly panel
#   "tool_result"       → show in Workspace Assembly panel
#   "learning_done"     → mark Learning panel as complete
#   "done"              → turn complete
```

---

## Workspaces

The conversation history panel becomes a **Workspaces panel** — a place to jump between isolated working contexts.

### What a Workspace Is

Each workspace is:
- Its own **Maestro session** (persistent conversation + workspace state)
- Its own **Learning session** (persistent conversation, parallel)
- A focused working area for a specific part of the project

### Shared Experience Across Workspaces

**Experience is the shared layer.** Context windows are isolated per workspace, but ALL Learning agents write to the same Experience. The super spends all morning in the "Electrical" workspace — Learning discovers routing rules and cross-references. They jump to "Mechanical" — Maestro there is already smarter because Experience updated globally.

Workspaces are isolated working memory. Experience is shared long-term memory.

### Creating Workspaces

**New Session [+]** creates a fresh workspace — clean Maestro context, clean Learning context, full Experience available from day one. The super organizes around whatever makes sense:
- "Electrical" — panel schedules, circuits, equipment connections
- "Mechanical" — HVAC, cooler, equipment
- "Site Work" — grading, utilities, concrete
- Or whatever fits their project and workflow

### Context Limits

Workspace conversations will eventually fill their context windows. Compression is the right long-term move — summarize and compact to keep the workspace alive longer. Not a priority for initial implementation. Experience carries forward regardless.

---

## Telegram Mode — Maestro on the Jobsite

Telegram is how Maestro meets the superintendent where they are — on the jobsite, phone in pocket.

### Same Brain, Different Interface

Telegram mode is the same Maestro Shell — same Knowledge, same Experience, same personality. The difference is the interface: text-message style, mobile-friendly.

Telegram Maestro has its own session (Maestro + Learning pair). It knows it's on Telegram. It knows which workspaces exist and can target them.

**What Telegram mode IS:**
- Conversational texting with Maestro — short, direct
- Can read from Knowledge and Experience
- Can take actions inside workspaces remotely
- The heartbeat channel (proactive outreach)
- An input channel for schedule updates, corrections, field conditions

**What Telegram mode is NOT:**
- Not a workspace replica — no ThinkingSection, no page cards, no bbox overlays
- Not where deep analysis happens — that's the workspace
- Not a separate brain — same Maestro, same Learning, everything feeds shared Experience

### Workspace Actions from Telegram

*"Go into my electrical workspace and pull up the panel details for the walk-in cooler."*

Maestro retrieves Pointers, assembles the workspace, adds pages and highlights. Responds: *"Got it. Come into the workspace to see the details."*

The **web app works on mobile and tablet.** iPad is for serious plan viewing (bigger screen). But the workspace UX works on phone too. "Come into the workspace" means opening the app on whatever device is handy.

### Telegram Bot Menu

Two commands from the Telegram BotFather menu:
- **Compact** — compress the conversation. Summarize older turns, free up context space, keep the thread alive.
- **Reset** — fresh conversation, same brain. Knowledge + Experience persist. Just like starting a new workspace.

The super controls when to reset. The brain is permanent — only the working memory resets.

### Telegram as Input Channel

Every Telegram message feeds Experience through Learning:
- *"Concrete guys are coming Thursday instead of Wednesday"* → schedule update
- *"That panel is 4B not 3A"* → correction, possible Knowledge edit or re-ground
- *"Vapor barrier crew needs to be here before the slab pour"* → sequencing knowledge
- *"We're doing everything in one pour"* → approach update

The super doesn't need to be in a workspace for Maestro to learn.

---

## The Complete Data Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                         UPLOAD TIME                                  │
│                                                                      │
│  Pass 1: Gemini full-page vision (EXISTS — don't touch)              │
│  → Pages + Pointers (bboxes + cropped images) + sheet reflections    │
│                           ↓                                          │
│  Pass 2: Per-Pointer enrichment agent (NEW — background job)         │
│  → Rich markdown descriptions + cross-refs + embeddings              │
│  → Input: cropped image + sheet reflection + page context            │
│                           ↓                                          │
│                      KNOWLEDGE                                       │
│          (atomic Pointers in Supabase, fully enriched)               │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                    ALWAYS LATEST
                           │
         ┌─────────────────┼─────────────────┐
         ↓                 ↓                 ↓
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  WORKSPACE   │  │  WORKSPACE   │  │   TELEGRAM   │
│ "Electrical" │  │ "Mechanical" │  │  + Heartbeat │
│  Maestro +   │  │  Maestro +   │  │  Maestro +   │
│  Learning    │  │  Learning    │  │  Learning    │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └─────────────────┼─────────────────┘
                         ↓
              ALL LEARNING AGENTS
              WRITE TO SHARED EXPERIENCE
                         ↓
┌──────────────────────────────────────────────────────────────────────┐
│                    EXPERIENCE (Supabase)                              │
│                                                                      │
│  Default files (always read by Maestro):                             │
│  ├── routing_rules.md (routes + index to extended files)             │
│  ├── corrections.md                                                  │
│  ├── preferences.md                                                  │
│  ├── schedule.md                                                     │
│  └── gaps.md                                                         │
│                                                                      │
│  Extended files (created by Learning, routed by routing_rules.md):   │
│  ├── walk_in_cooler.md                                               │
│  ├── subs/concrete.md                                                │
│  ├── daily_notes/2026-02-10.md                                       │
│  └── ...whatever the project needs                                   │
│                                                                      │
│  Learning manages this filesystem with full autonomy.                │
│  Learning writes instructions in routing_rules.md so Maestro         │
│  knows when to read extended files. Learning trains Maestro.         │
└──────────────────────────────────────────────────────────────────────┘
                         │
            ┌────────────┴────────────┐
            ↓                         ↓
     EXPERIENCE UPDATE          KNOWLEDGE UPDATE
     (shapes next query         (Learning edits Pointer
      in ANY session)            markdown directly, OR
                                 triggers re-ground →
                                 Brain Mode → new bbox →
                                 Pass 2 enrichment)
```

### Code Expression: API Routes (V3)

```python
# services/api/app/routers/v3_sessions.py — New router replacing queries.py

router = APIRouter(prefix="/v3", tags=["v3"])

# Session management
@router.post("/sessions")
async def create_session(
    project_id: UUID,
    session_type: str,          # 'workspace' | 'telegram'
    workspace_name: Optional[str] = None,
) -> dict:
    """Create a new session. Returns session_id."""
    ...

@router.get("/sessions/{session_id}")
async def get_session(session_id: UUID) -> dict:
    """Get session metadata + workspace state."""
    ...

@router.get("/sessions")
async def list_sessions(project_id: UUID) -> list[dict]:
    """List all active sessions for a project (workspaces + telegram)."""
    ...

@router.delete("/sessions/{session_id}")
async def close_session(session_id: UUID):
    """Close a session."""
    ...

@router.post("/sessions/{session_id}/reset")
async def reset_session(session_id: UUID) -> dict:
    """Reset (telegram). Fresh conversation, same brain. Returns new session_id."""
    ...

@router.post("/sessions/{session_id}/compact")
async def compact_session(session_id: UUID):
    """Compact (telegram). Compress older turns."""
    ...

# Query — the main interaction endpoint
@router.post("/sessions/{session_id}/query")
async def query(session_id: UUID, message: str) -> StreamingResponse:
    """
    Send a message to Maestro in this session.
    Returns SSE stream of events (tokens, thinking, workspace updates, done).
    """
    ...

# Experience (read-only for frontend — Learning writes via tools)
@router.get("/projects/{project_id}/experience")
async def list_experience(project_id: UUID) -> list[dict]:
    """List all Experience files for a project."""
    ...

@router.get("/projects/{project_id}/experience/{path:path}")
async def read_experience(project_id: UUID, path: str) -> dict:
    """Read a specific Experience file."""
    ...
```

---

## Implementation Path

### Phase 1: Enhanced Knowledge (Pass 2)
- [ ] Pointer enrichment_status, cross_references, enrichment_metadata columns (migration)
- [ ] experience_files table (migration)
- [ ] sessions table (migration)
- [ ] Pointer enrichment agent — takes cropped image + sheet reflection, writes rich markdown
- [ ] Background worker (run_pass2_worker) — polls pending, processes, writes back
- [ ] Startup reset: any 'processing' → 'pending' on server boot
- [ ] Embedding generation from enriched markdown (Voyage)
- [ ] Cross-reference extraction during enrichment
- [ ] Retry/failure handling per Pointer

### Phase 2: The Shell (Maestro)
- [ ] SessionManager — in-memory sessions with checkpoint to Supabase
- [ ] LiveSession dataclass with maestro_messages, learning_messages, workspace_state
- [ ] Session rehydration on server startup
- [ ] Checkpoint background loop (30s interval)
- [ ] New Maestro agent — one clean file (maestro_agent.py), model-agnostic, persistent conversation
- [ ] Model provider abstraction (providers.py) — route to Anthropic/OpenAI/Google/xAI
- [ ] Maestro tools: search_knowledge, read_pointer, read_experience, list_experience
- [ ] Workspace tools: add_pages, remove_pages, highlight_pointers, pin_page
- [ ] Experience injection — read default files every query, follow routing rules for extended files
- [ ] Seed default Experience files on project creation
- [ ] Gap awareness in system prompt + response generation
- [ ] MAESTRO_MODEL env var as config switch
- [ ] SSE streaming with workspace events + thinking events
- [ ] ThinkingSection — Workspace Assembly panel (cyan)
- [ ] V3 API routes (/v3/sessions, /v3/sessions/{id}/query)
- [ ] Gut the old system: remove big_maestro.py, agent.py fast/med/deep modes

### Phase 3: The Learning Agent
- [ ] Learning agent — persistent conversation, async alongside Maestro
- [ ] InteractionPackage: query + response + Pointers + Experience + workspace actions
- [ ] Experience filesystem tools: read_file, write_file, edit_file, list_files
- [ ] Knowledge read tools: read_pointer, read_page, search_knowledge
- [ ] Knowledge write tools: edit_pointer, edit_page, update_cross_references
- [ ] Re-ground trigger tool: trigger_reground(page_id, instruction)
- [ ] Learning background worker per session (processes queue at own pace)
- [ ] ThinkingSection — Learning panel (yellow) + Knowledge Update panel (purple)
- [ ] LEARNING_MODEL env var

### Phase 4: Workspaces
- [ ] Workspace creation (New Session [+])
- [ ] Workspaces panel (jump between isolated contexts)
- [ ] Shared Experience across all workspaces
- [ ] Per-workspace session management (create, resume, cleanup)
- [ ] Collapsed scrollable history per workspace

### Phase 5: Telegram Mode
- [ ] Telegram bot integration (BotFather setup)
- [ ] Telegram Maestro session (own conversation + own Learning)
- [ ] Channel-aware system prompt (knows it's on Telegram)
- [ ] Workspace awareness (list_workspaces, workspace_action tools)
- [ ] Compact command (compress conversation)
- [ ] Reset command (fresh conversation, same brain)
- [ ] Schedule input via Telegram conversation

### Phase 6: Heartbeat System
- [ ] Heartbeat scheduling (time-of-day, frequency)
- [ ] Runs through Telegram Maestro (same conversation, same context)
- [ ] Schedule × Knowledge × Experience cross-referencing
- [ ] Proactive insight generation (telling)
- [ ] Calculated scheduling questions (asking)
- [ ] Learning from heartbeat responses

### Phase 7: The Benchmark
- [ ] Benchmark logging (query + response + scores + Experience criteria)
- [ ] Emergent scoring from Learning findings
- [ ] Model comparison harness (replay queries, compare scores)
- [ ] Benchmark evolution tracking (is Maestro getting better over time?)
- [ ] User-facing confidence signals

---

## Key Decisions

### 2026-02-06 (Original Design)

1. **Three agents, not one.** Maestro (Shell), Learning (Benchmark Engine), Brain Mode (Knowledge Builder). Clear separation of concerns.

2. **Learning runs on every interaction.** There is always something to learn. Learning is the default state and the benchmark is continuous.

3. **The benchmark is emergent.** Scoring dimensions evolve from Learning's observations, not predefined rubrics.

4. **Experience IS the test suite.** Every learned behavior is also a benchmark criterion. Model swapping runs Experience as the eval.

5. **Gap awareness is partner intelligence.** Maestro is honest about what it doesn't know. Gap exploration is the highest-value Learning signal.

6. **Learning can re-ground Knowledge.** When corrections reveal vision errors, Learning spawns targeted Brain Mode agents to fix the source.

7. **The shell matters more than the model.** The model does text retrieval and synthesis from pre-built Knowledge. The shell is the product.

8. **The user is a collaborator.** The superintendent's domain expertise fills gaps. Maestro remembers it forever.

### 2026-02-07 (Expanded Design)

9. **Persistent conversations, not isolated calls.** Context windows live in memory on the server. The conversation IS the memory.

10. **Learning is eventually consistent.** Processes at its own speed. Experience updates land when they land.

11. **Workspaces, not conversation history.** Isolated context window pairs. Shared Experience.

12. **Telegram is Maestro's mobile mode.** Same brain, different interface, different tools.

13. **The schedule lives in the super's head.** Maestro helps externalize it through conversation.

14. **Heartbeats cross-reference Schedule × Knowledge × Experience.** The heartbeat is just another Maestro turn — Maestro initiates.

15. **ThinkingSection: three cognition panels, flipped layout.**

### 2026-02-08 (The Filing System Conversation)

16. **Gut the current system.** V3 is not an evolution — it's a replacement. The entire Maestro Mode agent system (big_maestro.py, agent.py, fast/med/deep modes, regex learning, stateless query/response) gets removed and replaced with V3.

17. **The filing system IS the wiring.** How data is stored and how it flows between agents defines the architecture. Two storage layers: hot (in-memory sessions) and cold (Knowledge + Experience in Supabase).

18. **Brain Mode Pass 2 is a background job.** Pass 1 exists and is perfect. Pass 2 enriches each Pointer with a dedicated agent that reads the cropped image + sheet reflection → rich markdown. Runs after Pass 1 completes, processes Pointers from a queue, independently retryable.

19. **Learning is an agent with a filesystem.** Not regex-based classification into predefined buckets. Learning has tools to read, write, create, and organize files in Experience. The Experience structure evolves based on what the project needs. Learning decides what to file and where.

20. **routing_rules.md is the index to all of Experience.** When Learning creates extended files, it updates routing_rules.md to tell Maestro when to read them. Learning trains Maestro's retrieval.

21. **Maestro always reads default Experience files.** Extended files are read when routing_rules.md instructs. Learning's job is to make sure Maestro is set up for future success.

22. **Learning edits Knowledge directly.** Text corrections (wrong numbers, wrong labels) are edited directly on the Pointer's markdown. Re-grounding is reserved for vision-level fixes (wrong bbox, missed region) — spawns Gemini to draw new bboxes, then queues for Pass 2.

23. **Learning has full read access to Knowledge.** It needs to see what Maestro saw to determine whether a correction needs a Knowledge edit, an Experience update, or a re-ground.

24. **Every Maestro session gets its own Learning.** Workspace Maestro + Learning pair. Telegram Maestro + Learning pair. All Learning agents write to shared Experience. All Maestro agents read shared Knowledge + Experience.

25. **Maestro knows where it is.** Workspace Maestro has workspace tools. Telegram Maestro has workspace-targeting tools. Same brain, different system prompts, different tool sets.

26. **The heartbeat runs through Telegram Maestro.** Same conversation, same context window. A scheduled trigger fires and Maestro takes a turn. Not a cold start — a continuation of the ongoing dialogue.

27. **Telegram Reset and Compact.** Reset = fresh conversation, same brain. Compact = compress older turns, keep the thread. The super controls their context window. The brain is permanent.

28. **The web app works on mobile and tablet.** Not tablet-only. iPad is for serious plan viewing. The workspace UX works everywhere.

29. **Stateful server.** Context windows live in memory for the duration of the session. Growing message array sent to the LLM each turn. The server IS the state. Fundamental shift from the current stateless architecture.

30. **Session persistence.** Sessions checkpoint to Supabase every 30 seconds. If Railway restarts, sessions rehydrate from the last checkpoint. The user picks up right where they left off. (2026-02-08)

31. **Pass 2 queue is in-process asyncio.** No external job queue (no Redis, no Celery). Background asyncio worker polls pending Pointers from the database. On server restart, any 'processing' status resets to 'pending'. Simple, no new infrastructure. (2026-02-08)

32. **Model config is per-instance.** MAESTRO_MODEL and LEARNING_MODEL are environment variables. Change on Railway dashboard, redeploy. No per-project or runtime switching in v1. (2026-02-08)

---

*This document supersedes all previous architecture versions. V3 is a clean slate — the partner.*
*Last updated: 2026-02-08*
