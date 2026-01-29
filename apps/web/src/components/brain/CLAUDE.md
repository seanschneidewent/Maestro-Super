# Brain Mode Components

Navy-themed setup interface for project configuration. This is where superintendents (or project managers) upload construction documents and the system processes them into structured context.

## Structure

### Main Container
- **BrainMode.tsx** — Main container orchestrating file upload, processing status, and the three-panel layout (file tree | mind map | context panel)

### File Navigation
- **FolderTree.tsx** — Hierarchical file browser showing uploaded PDFs organized by discipline
- **DriveImportButton.tsx** — Google Drive integration for importing files directly

### Mind Map (`mind-map/`)
Project visualization as an interactive node graph:
- **ContextMindMap.tsx** — ReactFlow-based mind map showing project → disciplines → pages → pointers
- **nodes/** — Custom node components:
  - `ProjectNode.tsx` — Root project node
  - `DisciplineNode.tsx` — Discipline groupings (Architectural, Structural, etc.)
  - `PageNode.tsx` — Individual drawing pages
  - `PointerNode.tsx` — Context pointers (details, callouts, notes)
  - `DetailNode.tsx` — Detail references

### Context Panel (`context-panel/`)
Right-side panel showing details for selected items:
- **ContextPanel.tsx** — Container that switches between detail views
- **PageContextView.tsx** — Full page view with PDF rendering
- **PageDetail.tsx** — Page metadata and pointer list
- **DisciplineDetail.tsx** — Discipline-level summary
- **PointerDetail.tsx** — Individual pointer details with bbox highlighting
- **BboxOverlay.tsx** — Draws bounding boxes on page images
- **RoleLegend.tsx** — Legend for pointer role colors

### Processing UI
- **UploadProgressModal.tsx** — Modal showing upload + PNG rendering progress
- **ProcessingBar.tsx** — Inline progress bar for page-by-page processing
- **ProcessingNotification.tsx** — Toast notifications for processing status
- **PageThumbnailModal.tsx** — Large thumbnail preview modal
- **PdfViewer.tsx** — PDF.js-based viewer for full document viewing

## Data Flow

```
User selects files
       │
       ▼
Upload to Supabase Storage (PDFs)
       │
       ▼
POST /projects/{id}/pages (creates page records)
       │
       ▼
Backend renders PNGs + starts processing job
       │
       ▼
Frontend polls via SSE (/projects/{id}/processing/stream)
       │
       ▼
useProcessingStream updates UI as pages complete
       │
       ▼
Mind map + context panel reflect processed data
```

## Key Patterns

- **State persistence**: `brainState` prop preserves selection across mode switches
- **Optimistic UI**: File tree updates immediately on upload, refetches on completion
- **SSE streaming**: Real-time processing updates via `useProcessingStream` hook
- **Lazy loading**: Page thumbnails load on-demand, not all at once
