# Agent Workspace UX — Implementation Phase 1
## Vertical Page Workspace

### Intent
Transform the current Maestro query results display from a chat-style response into a **vertical scrollable page workspace**. When Maestro finds relevant pages for a query, they appear as a vertical list with page images, bbox overlays, and processing states.

### Current Architecture
- **Frontend:** React + Vite + TypeScript at `apps/web/`
- **Backend:** FastAPI at `services/api/`
- **Current query flow:** User types query → POST `/projects/{id}/query` → SSE stream → frontend renders response with page cards
- **Current page display:** `PlansPanel.tsx` shows page thumbnails in a side panel with bbox overlays
- **SSE events:** `thinking`, `page_found`, `annotated_image`, `code_execution`, `code_result`, `search_complete`, `response_chunk`, `done`

### What Exists (key files to understand)
- `apps/web/src/components/maestro/MaestroMode.tsx` — Main Maestro query interface
- `apps/web/src/components/maestro/PlansPanel.tsx` — Current page display panel
- `apps/web/src/components/maestro/QueryHistoryPanel.tsx` — Conversation history
- `apps/web/src/hooks/useProcessingStream.ts` — SSE event handler for Brain Mode processing
- `apps/web/src/lib/api.ts` — API client
- `apps/web/src/components/brain/context-panel/PageDetail.tsx` — Page detail with bbox rendering

### What to Build

#### 1. Page Workspace Component (`PageWorkspace.tsx`)
A new component that replaces the current PlansPanel for query results display:

- **Vertical scrollable list** of page cards (not tabs, not side panel)
- Each card shows:
  - Page name header (e.g., "E-3.2 Panel Schedule")
  - Page image (loaded from Supabase storage via existing image URLs)
  - Bbox overlays on the image (SVG overlay, same pattern as existing PageDetail component)
  - Processing state badge (⏳ Queued, 🔬 Processing, ✅ Done)
- Cards appear one at a time as `page_found` SSE events arrive
- Bboxes appear in real-time as `annotated_image` or bbox SSE events arrive
- **Pin/Unpin button** on each card (📌 toggle)
- Pinned pages cannot be removed

#### 2. Page State Machine
Each page in the workspace has a state:
```typescript
type PageState = 'queued' | 'processing' | 'done' | 'pinned';

interface WorkspacePage {
  pageId: string;
  pageName: string;
  imageUrl: string;
  state: PageState;
  pinned: boolean;
  bboxes: BBox[];  // accumulates as they arrive
}
```

#### 3. Integration with Existing Query Flow
- When a query starts, the Page Workspace appears (replacing or alongside the current response display)
- `page_found` events add pages to the workspace
- `annotated_image` events add bbox data to specific pages
- `response_chunk` events still update the text response (which will become the "Evolved Response" later)
- `done` event marks all pages as done

### Constraints
- **DO NOT modify backend** — this is frontend-only for Phase 1
- **DO NOT delete existing components** — add new ones alongside, wire up with feature flag or conditional render
- **DO NOT break production** — work on `feature/local-dev-setup` branch only
- **Reuse existing patterns** — look at how PageDetail.tsx renders bbox overlays, use same approach
- **Mobile-first** — vertical scroll works on all screen sizes
- **TypeScript strict** — no `any` types

### Environment
- OS: Windows 10, PowerShell
- Node: v22.20.0
- Frontend dev server: http://localhost:3000
- Backend: http://localhost:8000
- Branch: `feature/local-dev-setup`
- Working dir: `C:\Users\Sean Schneidewent\Maestro-Super`

### Implementation Order
1. Read and understand MaestroMode.tsx, PlansPanel.tsx, PageDetail.tsx
2. Create PageWorkspace.tsx with the vertical list layout
3. Create WorkspacePage card component
4. Wire page_found SSE events to add pages
5. Wire bbox events to update page bboxes
6. Add pin/unpin functionality
7. Add processing state badges
8. Test with the local dev environment

### Commit Convention
Make small, focused commits. Message format: `feat(workspace): description`

When completely finished, run this command to notify:
openclaw gateway wake --text "Done: Page Workspace component implemented" --mode now
