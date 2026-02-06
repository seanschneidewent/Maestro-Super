# Phase 4: Workspaces + Full Frontend

## Context

Read `maestro/MAESTRO-ARCHITECTURE-V3.md` — it is the alignment doc for the entire V3 architecture. This phase builds the multi-workspace UX.

**Look at the Phase 1-3 commits to understand what was built.** Phase 3 delivered:
- Learning agent running alongside Maestro
- Experience grows automatically from every interaction
- Knowledge editing + re-ground capabilities
- ThinkingSection with all three panels active (cyan, yellow, purple)

**Current state:** The app has a single workspace session per project. This phase adds multiple named workspaces with shared Experience.

## Goal

1. **Workspaces panel** — Replace the old conversation history panel with a Workspaces panel where users create, switch, and manage isolated working contexts
2. **Multi-workspace sessions** — Each workspace has its own Maestro + Learning pair, all sharing one Experience
3. **Workspace lifecycle** — Create, resume, close. Idle cleanup.
4. **Full frontend polish** — Scrollable history with collapsed turns, flipped layout finalized, mobile-responsive

## What This Phase Delivers

After this phase ships:
- Super sees a Workspaces panel listing their working contexts ("Electrical", "Mechanical", "Site Work")
- "New Workspace [+]" creates a fresh workspace — clean conversation, full Experience from day one
- Clicking a workspace switches to it — loads its session, restores conversation + workspace state
- Experience learned in one workspace makes all others smarter
- Scrollable history with collapsed turns, expandable to audit cognition
- Full V3 visual design on mobile, tablet, and desktop

## Detailed Requirements

### R1: Workspaces Panel

**Create `apps/web/src/components/maestro/WorkspacesPanel.tsx`:**

Replaces the old `QueryHistoryPanel.tsx` (removed in Phase 2).

Visual design:
- Sidebar panel (same position as old conversation history)
- Lists workspaces for the current project: name, last active time, preview of last message
- "New Workspace [+]" button at top
- Active workspace is highlighted
- Click a workspace → switch to it
- Swipe/long-press → close workspace option

Data:
- `GET /v3/sessions?project_id=...` returns all workspace sessions
- Each session has `workspace_name`, `last_active_at`, `status`
- Filter to `session_type='workspace'` and `status IN ('active', 'idle')`

### R2: Workspace Creation Flow

**"New Workspace [+]" interaction:**
1. Taps [+] → prompt for workspace name (or auto-generate: "Workspace 1", "Workspace 2", etc.)
2. `POST /v3/sessions` with `session_type='workspace'` and `workspace_name`
3. Returns new `session_id`
4. Switch to the new workspace — empty conversation, empty workspace, full Experience

**Auto-naming:** If the user doesn't provide a name, auto-generate based on count. They can rename later.

### R3: Workspace Switching

When the user clicks a workspace in the panel:
1. If currently in a workspace, disconnect the SSE stream for the current session
2. Load the target session: `GET /v3/sessions/{session_id}`
3. Restore:
   - Conversation history (render all past turns with collapsed ThinkingSections)
   - Workspace state (displayed pages, highlighted Pointers, pinned pages)
4. Connect new SSE stream for the target session
5. Ready for next query

**Key UX:** Switching should feel instant. The conversation and workspace state are loaded from the session endpoint. Pages in the workspace state need their images fetched (can lazy-load).

### R4: Shared Experience Visibility

Experience is shared across all workspaces (all Learning agents write to the same `experience_files` for the project).

When the user switches from "Electrical" to "Mechanical", Maestro in "Mechanical" reads the latest Experience — including anything learned in "Electrical". This is invisible to the user but makes Maestro feel smarter.

**No UI change needed for this** — it's already how the backend works (Phase 2 reads Experience per-query from the shared table). But verify the behavior works correctly across workspace switches.

### R5: Session History Rendering

**Modify `apps/web/src/components/maestro/MaestroMode.tsx`:**

When loading a session (on switch or page refresh), render the full conversation history:

Each historical turn renders as a collapsed group:
```
  [Maestro Response summary — first ~100 chars]
  🔵🟡 (cognition indicator dots)
  [User query text]
```

Tap to expand → shows full response + all three ThinkingSection panels for that turn.

**Current turn:** fully expanded (response streaming + live cognition panels).

**Data source:** `session.maestro_messages` from the session endpoint contains the full message array. The SSE events from past turns need to be stored or reconstructed for the ThinkingSection panels.

**Approach for historical cognition:** Store ThinkingSection content per-turn alongside the messages. Options:
- Store thinking content in `maestro_messages` as metadata on each assistant message
- Or store as a separate array in the session state
- Choose the approach that Phase 2 set up (check the session checkpoint structure)

### R6: Backend — Workspace Management Enhancements

**Modify `services/api/app/routers/v3_sessions.py`:**

Add endpoints:
- `PATCH /v3/sessions/{session_id}` — rename workspace (`workspace_name`)
- `GET /v3/sessions/{session_id}/history` — return rendered conversation history with cognition data for each turn

**Modify `services/api/app/services/v3/session_manager.py`:**

Add:
- `list_sessions(project_id, session_type?, status?, db)` — filtered session listing
- Idle session cleanup: sessions inactive for >24h get status set to 'idle'. Idle sessions can still be resumed. Sessions idle for >7 days get closed.

### R7: Frontend — Layout Polish

**Finalize the flipped layout from the V3 doc:**

```
┌─────────────────────────────────────────┐
│ [Workspaces Panel]  │  WORKSPACE         │
│                     │  (pages, bboxes)   │
│  Electrical ●       │                    │
│  Mechanical         │  Response          │
│  Site Work          │  🔵 Assembly       │
│  [+ New Workspace]  │  🟡 Learning       │
│                     │  🟣 Knowledge      │
│                     │  "User query"      │
│                     │                    │
│                     │  [Ask about...]    │
└─────────────────────────────────────────┘
```

- Workspaces panel on the left (collapsible on mobile)
- Workspace (pages + bboxes) and conversation in the main area
- Responsive: on mobile, workspaces panel is a drawer/overlay
- On tablet/desktop, workspaces panel is a sidebar

**Mobile-first:** The workspace should work well on phone screens. Pages scroll vertically. Conversation is below the workspace area (or togglable).

### R8: Frontend — Workspace State Persistence

When the user refreshes the page:
1. Check for active session in local storage or URL parameter
2. If found: `GET /v3/sessions/{session_id}` → restore everything
3. If not found: show Workspaces panel, let them pick or create

When the server restarts (Railway redeploy):
1. User's next request triggers session rehydration
2. SessionManager loads the session from Supabase
3. User continues where they left off — no visible interruption

## Constraints

- **Do NOT modify Maestro or Learning agent behavior** — Phases 2 and 3 stay as-is
- **Experience sharing is already handled** — just verify it works across workspace switches
- **Keep workspace visual components from Phase 2** — PageWorkspace, WorkspacePageCard, BboxOverlay stay
- **Historical ThinkingSection data** — if Phase 2 didn't store cognition content per-turn, you'll need to add that storage now. Keep it simple (JSONB on the session or per-message metadata).

## File Map

```
NEW FILES:
  apps/web/src/components/maestro/WorkspacesPanel.tsx

MODIFIED FILES:
  apps/web/src/components/maestro/MaestroMode.tsx     (workspace switching, history rendering)
  apps/web/src/components/maestro/ThinkingSection.tsx  (collapsed historical turn rendering)
  apps/web/src/hooks/useSession.ts                    (multi-session support, switching)
  services/api/app/routers/v3_sessions.py             (PATCH, history endpoint)
  services/api/app/services/v3/session_manager.py     (list_sessions, idle cleanup)
```

## Environment

- **OS:** Windows 10 (dev), Linux (Railway production)
- **Frontend:** React + TypeScript + Vite + TailwindCSS
- **Backend:** FastAPI + SQLAlchemy + Supabase
- **Repo:** `C:\Users\Sean Schneidewent\Maestro-Super`
