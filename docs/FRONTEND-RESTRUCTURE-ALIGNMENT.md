# Frontend Restructure — Agent Workspace UX Alignment

**Date:** 2026-02-04
**Scope:** Frontend only. React/TypeScript. Zero backend changes. Zero Gemini prompt changes.
**Branch:** `main` (production)
**Goal:** Transform the current chaotic feed layout into the Agent Workspace described in `maestro/AGENT-WORKSPACE-UX.md`

---

## Intent

The Maestro orchestrator pipeline is working correctly on production (viewm4d.com). It selects pages via Fast Mode, fires parallel Deep agents per page, streams SSE events (page_state, response_update, annotated_image, thinking, etc.), and returns findings with bboxes.

**The problem is purely frontend.** The UI renders everything in a messy feed — duplicate page thumbnails, agentic vision crops as separate images, missing evolved response, half-width thinking section, and a mode toggle that shouldn't exist.

**The target state** is a clean vertical layout:
1. **Page Workspace** (top) — vertical scrollable page cards with bbox overlays from Deep Mode
2. **Thinking Section** (middle) — full-width, centered, prominent timeline
3. **Evolved Response** (below thinking) — single text block that grows as Deep agents complete
4. **Query Input** (bottom, fixed) — no mode toggle, single unified interface
5. **Nothing below the input** — no old page thumbnails, no annotated image grid

---

## Architecture Discovery

### Component Tree (relevant files)

```
apps/web/src/
├── components/maestro/
│   ├── MaestroMode.tsx         — Main orchestrator component, manages state, renders layout
│   ├── FeedViewer.tsx          — Renders the scrollable feed of items (pages, text, findings, etc.)
│   ├── PageWorkspace.tsx       — Vertical page card list (NEW, already built)
│   ├── WorkspacePageCard.tsx   — Individual page card with bbox overlays (NEW, already built)
│   ├── EvolvedResponse.tsx     — Incremental response display (NEW, built but NEVER RENDERED)
│   ├── ThinkingSection.tsx     — Trace/thinking timeline (exists, needs layout fix)
│   ├── FindingBboxOverlay.tsx  — Renders finding bboxes as positioned overlays
│   ├── HoldToTalk.tsx          — Contains QueryInput component with mode toggle
│   ├── PageWorkspace.tsx       — Re-exports types from WorkspacePageCard
│   └── index.ts                — Barrel exports
├── hooks/
│   ├── useQueryManager.ts      — SSE streaming, processes all event types including page_state/response_update/learning
│   └── useWorkspacePages.ts    — Workspace page state management (add, sync, bbox, findings, pin)
└── types/
    └── query.ts                — Type definitions
```

### Current Data Flow

1. User submits query → `useQueryManager.submitQuery()` → SSE stream opens
2. SSE events processed in `processEvent()`:
   - `page_state` → updates `queryState.pageAgentStates` (queued/processing/done per page)
   - `response_update` → updates `queryState.evolvedResponseText` + `evolvedResponseVersion`
   - `learning` → appends to `queryState.learningNotes`
   - `annotated_image` → appends to `queryState.annotatedImages`
   - `tool_result` (select_pages) → builds `queryState.selectedPages`
   - `done` → fires `onQueryComplete` callback with all accumulated data
3. `MaestroMode.handleQueryComplete()` receives `CompletedQuery`, builds `feedItems`:
   - Adds `pages` feed item (old-style clickable thumbnails) ← **DUPLICATE, REMOVE**
   - Adds `annotated-images` feed item (crop thumbnails) ← **WRONG FORMAT, REMOVE**
   - Adds `findings` feed item (Concept Findings card) ← **KEEP but reposition**
   - Adds `text` feed item (final answer + ThinkingSection) ← **REPLACE with EvolvedResponse**
4. `FeedViewer` renders feed items in order:
   - `PageWorkspace` at top (from `workspacePages` prop) ← **CORRECT, KEEP**
   - Then `feedItems.map()` renders each item ← **NEEDS RESTRUCTURE**
5. During streaming, `useWorkspacePages.syncFromSelectedPages()` populates workspace cards
6. After completion, `markWorkspaceDone()` sets all workspace pages to "done"

### What's Built But Not Wired

- **`EvolvedResponse` component** — Renders markdown text + page agent progress badges + learning notes. Uses dark theme (prose-invert). **Never imported or rendered anywhere.**
- **`useQueryManager` orchestrator fields** — `evolvedResponseText`, `evolvedResponseVersion`, `pageAgentStates`, `learningNotes` are all tracked in QueryState but never passed to any component.
- **`useWorkspacePages.syncFromPageAgentStates()`** — Exists but never called. Should be called during streaming to update workspace card states from `page_state` SSE events.

### What Needs Changing

| File | Change |
|------|--------|
| `MaestroMode.tsx` | Stop adding `pages` and `annotated-images` to feedItems. Remove `queryMode` state and mode toggle props. Wire EvolvedResponse. Wire `pageAgentStates` → workspace sync. |
| `FeedViewer.tsx` | Remove `pages`, `annotated-images` case handlers. Add EvolvedResponse rendering. Fix ThinkingSection layout. Restructure feed order. |
| `ThinkingSection.tsx` | Change from `w-1/2` to full-width centered (`w-full max-w-3xl mx-auto`). |
| `EvolvedResponse.tsx` | Change from dark theme (prose-invert) to light theme matching the app. |
| `HoldToTalk.tsx` (QueryInput) | Remove mode toggle button and related props. |

---

## Requirements

### R1: Remove Duplicate Page Rendering

In `MaestroMode.tsx` → `handleQueryComplete()`:

**Remove** the block that adds `type: 'pages'` feed item (around line where it pushes `{ type: 'pages', ... }`).

**Remove** the block that adds `type: 'annotated-images'` feed item.

In `FeedViewer.tsx`:
- Remove the `case 'pages':` handler that renders `PagesCluster`.
- Remove the `case 'annotated-images':` handler that renders crop thumbnails.
- Remove the `PagesCluster` component (it's now unused).
- Remove the `FeedPageItemDisplay` component (now unused).
- Keep the `ExpandedPageModal` component (it may be useful for workspace page tap-to-zoom later).

Also remove the `annotated-images` feed item from `handleQueryComplete` in `MaestroMode.tsx`, and from the `FeedItem` union type in `FeedViewer.tsx`.

Do NOT remove the `standalone-page` type — that's used for file tree browsing.

### R2: Wire Page Agent States to Workspace During Streaming

In `MaestroMode.tsx`, add a `useEffect` that watches `activeQuery?.pageAgentStates` and calls `syncFromPageAgentStates()`:

```typescript
// Already imported: useWorkspacePages has syncFromPageAgentStates
const pageAgentStates = activeQuery?.pageAgentStates ?? [];

useEffect(() => {
  if (isStreaming && pageAgentStates.length > 0) {
    syncFromPageAgentStates(pageAgentStates);
  }
}, [isStreaming, pageAgentStates, syncFromPageAgentStates]);
```

This requires destructuring `syncFromPageAgentStates` from the `useWorkspacePages()` hook call (it's already returned but not destructured in MaestroMode).

### R3: Fix ThinkingSection Layout

In `ThinkingSection.tsx`, change the root div class from:
```
w-1/2 rounded-xl border border-slate-200 bg-slate-50/50 ...
```
to:
```
w-full max-w-3xl mx-auto rounded-xl border border-slate-200 bg-slate-50/50 ...
```

This makes it full-width up to a readable max, centered in the layout.

### R4: Render EvolvedResponse in FeedViewer

The `EvolvedResponse` component exists but uses dark theme classes (`prose-invert`, `text-slate-200/90`, `bg-amber-500/5`, etc.). Update it to use light theme matching the rest of the app:

- `prose-invert` → remove (use default prose)
- `text-slate-200/90` → `text-slate-700`
- `text-amber-200/80` → `text-amber-700`
- `text-amber-400` → `text-amber-500`
- `bg-amber-500/5` → `bg-amber-50 border-amber-200`
- `bg-emerald-500/15 text-emerald-300 border-emerald-500/20` → `bg-emerald-100 text-emerald-700 border-emerald-200`
- `bg-cyan-500/15 text-cyan-300 border-cyan-500/20` → `bg-cyan-100 text-cyan-700 border-cyan-200`
- `bg-slate-500/15 text-slate-400 border-slate-500/20` → `bg-slate-100 text-slate-500 border-slate-200`
- `text-slate-400` (footer) → `text-slate-500`
- `text-slate-500` (version) → `text-slate-400`

Wrap EvolvedResponse in a card container matching the app style:
```
<div className="w-full max-w-3xl mx-auto bg-white/90 backdrop-blur-md border border-slate-200/60 rounded-2xl shadow-sm p-4 md:p-6">
```

In `FeedViewer.tsx`, import and render `EvolvedResponse` between the ThinkingSection and the query input area. It should appear:
- **During streaming**: Shows evolvedResponseText growing, with page agent progress badges
- **After completion**: Shows final synthesized response

Pass these props from `FeedViewerProps` (add new props):
- `evolvedResponseText: string`
- `evolvedResponseVersion: number`
- `pageAgentStates: PageAgentState[]`
- `learningNotes: LearningNote[]`

In `MaestroMode.tsx`, pass the orchestrator state to FeedViewer:
```typescript
evolvedResponseText={activeQuery?.evolvedResponseText ?? ''}
evolvedResponseVersion={activeQuery?.evolvedResponseVersion ?? 0}
pageAgentStates={activeQuery?.pageAgentStates ?? []}
learningNotes={activeQuery?.learningNotes ?? []}
```

### R5: Remove Mode Toggle

In `HoldToTalk.tsx` (which exports `QueryInput`):
- Remove the `queryMode` prop
- Remove the `onQueryModeChange` prop
- Remove the mode toggle button JSX (the button that cycles fast → med → deep)
- Keep the rest of QueryInput intact (text input, submit, voice)

In `MaestroMode.tsx`:
- Remove the `queryMode` state variable (`useState<'fast' | 'med' | 'deep'>('fast')`)
- Remove `queryMode` and `onQueryModeChange` props from `<QueryInput>`
- When calling `submitQuery()`, always pass `'deep'` as the mode (since Big Maestro handles everything as deep)
- Remove `queryMode` from user-query feed items (or default it to `'deep'`)
- Remove the `ModeBadge` from user-query feed items display

### R6: Restructure FeedViewer Layout

The new render order in FeedViewer's main return should be:

```
<div ref={scrollContainerRef} className="flex-1 overflow-y-auto ...">
  <div className="space-y-6 w-full" style={{ maxWidth: containerWidth }}>

    {/* 1. Workspace pages (already here) */}
    {workspacePages && workspacePages.length > 0 && (
      <PageWorkspace pages={workspacePages} onTogglePin={onWorkspaceTogglePin} />
    )}

    {/* 2. Thinking Section (streaming or completed) */}
    {(isStreaming || hasTrace) && (
      <ThinkingSection ... />
    )}

    {/* 3. Evolved Response */}
    {(evolvedResponseText || pageAgentStates.length > 0) && (
      <div className="w-full max-w-3xl mx-auto">
        <EvolvedResponse ... />
      </div>
    )}

    {/* 4. Findings card (if available from completed queries) */}
    {feedItems.filter(item => item.type === 'findings').map(...)}

    {/* 5. User query bubbles (conversation history) */}
    {feedItems.filter(item => item.type === 'user-query').map(...)}

  </div>
</div>
```

The key change: ThinkingSection and EvolvedResponse are rendered as **top-level layout elements**, not inside individual feed items. The feed items only handle user queries and findings now.

For the completed state (not streaming), the ThinkingSection should render from the `text` feed item's trace data. Keep the `text` feed item type but ONLY use it for the ThinkingSection trace — the response text is now shown by EvolvedResponse instead.

Actually, simpler approach: Keep `text` feed items but change how they render:
- Remove the markdown response card from `text` item rendering
- Keep ThinkingSection rendering from `text` items (for completed query traces)
- EvolvedResponse handles ALL response text display

### R7: Wire Findings Bboxes to Workspace Pages

Currently, `handleQueryComplete` calls `syncWorkspacePages(query.pages, query.conceptResponse?.findings)` — this already passes findings to the workspace hook.

In `useWorkspacePages.syncFromSelectedPages()`, findings are already filtered per-page and stored in `WorkspacePage.findings`.

In `WorkspacePageCard`, `FindingBboxOverlay` is already rendered when `page.findings.length > 0`.

**Verify this works end-to-end.** If findings bboxes aren't appearing on workspace cards, check:
1. The `conceptResponse.findings` have `pageId` that matches the workspace page IDs
2. The findings have valid `bbox` arrays (4 numbers, normalized 0-1)
3. `FindingBboxOverlay` correctly filters by `pageId`

This should already work from existing code — just verify after the other changes.

---

## Constraints

- **DO NOT modify any backend files** (nothing in `services/` or `app/`)
- **DO NOT modify any Gemini prompts or AI configuration**
- **DO NOT break conversation history restore** (`handleRestoreConversation` in MaestroMode.tsx) — this needs to still rebuild feed items from past queries. The `pages` type may still be needed for history restore; if so, keep the type but don't render old-style thumbnails — render via workspace instead.
- **DO NOT break standalone page viewing** (file tree → page viewer)
- **DO NOT break the streaming flow** — SSE events must continue to work
- **DO NOT remove `PagesCluster`/`FeedPageItemDisplay` if they're used by conversation history restore** — check `handleRestoreConversation` carefully. If it adds `pages` feed items, those need an alternative render path.
- **Keep `vite build` passing** — no TypeScript errors
- **Production-safe** — this goes straight to Vercel via main branch

---

## Implementation Order

1. **R3** (ThinkingSection layout fix) — smallest, safest change
2. **R5** (Remove mode toggle) — isolated to HoldToTalk.tsx + MaestroMode.tsx
3. **R4** (EvolvedResponse light theme + render wiring) — add new rendering
4. **R1** (Remove duplicate pages/annotated-images) — remove old rendering
5. **R2** (Wire page agent states to workspace) — streaming improvement
6. **R6** (Restructure FeedViewer layout) — the big restructure, depends on R1/R3/R4
7. **R7** (Verify findings bboxes on workspace) — verification pass

---

## Environment

- **OS:** Windows 11 (PowerShell)
- **Node:** v22.20.0
- **Package Manager:** pnpm (workspace: `apps/web`)
- **Build:** `cd apps/web && npx vite build` (verify no errors)
- **Framework:** React 18 + TypeScript + Vite + TailwindCSS
- **Repo root:** `C:\Users\Sean Schneidewent\Maestro-Super`

---

## Conversation History Restore — Important Note

`handleRestoreConversation()` in MaestroMode.tsx rebuilds `feedItems` from API query data. It currently adds `pages` feed items for each historical query. When removing the `pages` case from FeedViewer rendering:

**Option A (Recommended):** Keep `pages` as a valid FeedItem type but don't render it in FeedViewer (return null for that case). Instead, on conversation restore, populate the workspace pages from the last query's cached pages. The workspace already shows page cards — no need for the old thumbnail grid even in history.

**Option B:** Convert all `pages` feed items to `workspace` feed items in the restore function. More complex, less safe.

Go with Option A. The `pages` case in the switch simply returns `null`.

---

## Testing Checklist

After all changes:
1. `cd apps/web && npx vite build` passes with zero errors
2. Fresh query on production: pages appear in workspace cards (not as old thumbnails)
3. During streaming: workspace cards show queued → processing → done states
4. During streaming: ThinkingSection appears centered, full-width
5. During streaming: EvolvedResponse appears below thinking, grows as agents complete
6. After completion: no duplicate page thumbnails below the query
7. After completion: no annotated image crop thumbnails
8. No mode toggle button on query input
9. File tree page selection still works (standalone viewer)
10. Conversation history restore still works (past queries load correctly)
11. New conversation button clears everything properly
