# V3 Frontend Impact Analysis

*Which files need changes to wire old frontend → V3 backend*

---

## Files That STAY EXACTLY THE SAME

### Brain Mode (100% unchanged)
```
components/brain/BrainMode.tsx           # Upload, Pass 1 display - no V3 changes
components/brain/FileTree.tsx            # File navigation - unchanged
components/brain/PageDetailPanel.tsx     # Page viewer - unchanged
components/brain/MindMap.tsx             # Mind map view - unchanged
```

Brain Mode calls existing endpoints that V3 didn't touch:
- `POST /projects/{id}/upload` 
- `GET /projects/{id}/pages`
- `GET /pages/{id}/pointers`

### UI Components (unchanged)
```
components/ModeToggle.tsx                # Brain/Maestro switch - unchanged
components/ui/*                          # All UI primitives - unchanged
components/maestro/PageWorkspace.tsx     # Page display + bbox overlays - unchanged
components/maestro/WorkspacePageCard.tsx # Page card component - unchanged
components/maestro/BboxOverlay.tsx       # Bbox rendering - unchanged
```

### Utilities (unchanged)
```
lib/api.ts                               # API client - unchanged
lib/supabase.ts                          # Supabase client - unchanged
lib/storage.ts                           # Storage helpers - unchanged
```

---

## Files That NEED CHANGES

### High Impact (Core Query Flow)

```
hooks/useQueryManager.ts                 # ← MAIN CHANGE NEEDED
```
**Current:** Calls `POST /projects/{id}/queries/stream`
**V3:** Need to call `POST /v3/sessions/{id}/query`
**Changes:**
1. Create/resume session on mount
2. Change API endpoint
3. Map V3 SSE events → current state shape

### Medium Impact (Display)

```
components/maestro/ThinkingSection.tsx   # May need 3-panel support
components/maestro/MaestroMode.tsx       # May need session state
```

**ThinkingSection:** Currently single panel. V3 has 3 panels (workspace_assembly, learning, knowledge_update). Could add panels incrementally or keep single panel initially.

**MaestroMode:** May need to track sessionId in state. Minimal change.

### Low Impact (Types)

```
types/index.ts                           # Add V3 session types
```

---

## Recommended Change Order

### Phase 1: Make Queries Work (1-2 hours)
1. Add session creation to `useQueryManager.ts`
2. Change endpoint from `/queries/stream` → `/v3/sessions/{id}/query`
3. Map V3 SSE events → current state (token→answer, workspace_update→pages)

### Phase 2: Add Learning Panel (optional, 1 hour)
1. Extend ThinkingSection with learning panel
2. Route `thinking` events with `panel: "learning"` to it
3. Style with yellow theme per V3 spec

### Phase 3: Add Workspaces (optional, 2-3 hours)
1. Add WorkspacesPanel component (already built in V3, can adapt)
2. Add session switching to MaestroMode
3. Style as collapsible sidebar

---

## SSE Event Mapping

| Old Event | V3 Event | Action |
|-----------|----------|--------|
| `trace` | `thinking` (panel: workspace_assembly) | Route to trace display |
| `pages` | `workspace_update` (action: add_pages) | Update selected pages |
| `answer` | `token` | Append to response text |
| `concept_response` | - | V3 doesn't have this; response is in tokens |
| `mode` | - | V3 doesn't use modes; remove |
| `learning` | `thinking` (panel: learning) | New panel or ignore |
| - | `tool_call`, `tool_result` | Show in trace or ignore |
| - | `done` | Mark complete |

---

## State Shape Differences

### Current State (useQueryManager)
```typescript
{
  trace: AgentTraceStep[]
  selectedPages: AgentSelectedPage[]
  thinkingText: string
  finalAnswer: string
  displayTitle: string | null
  currentTool: string | null
  mode: 'fast' | 'med' | 'deep'
  // ...
}
```

### V3 State (would need)
```typescript
{
  sessionId: string
  turns: MaestroTurn[]
  workspacePages: string[]
  highlightedPointers: string[]
  // ...
}
```

**Approach:** Keep current state shape internally, just populate it from V3 events. Less disruptive.

---

## Summary

**Minimal change path:**
1. One hook file gets the session wiring (~100 lines)
2. Everything else stays the same
3. Brain/Maestro toggle, page workspace, bbox overlays — all unchanged
4. Incremental: add Learning panel later if wanted

**The old UI can work with V3 backend with changes to ONE file.**

---

*Analysis complete. Ready for discussion with Sean.*
