# CLAUDE.md - Instructions for Claude Code

## Project Overview

Maestro Super is a clean rewrite of a construction plan analysis system. The architecture is documented in `docs/ARCHITECTURE.md` - read it first.

## Reference Implementation

The prototype lives at: `/Users/sean/Maestro4D/Maestro4D-1/apps/web-internal/`

**When to reference:**
- Exact Gemini prompt text for the three-pass pipeline
- Specific coordinate math edge cases
- OCR integration patterns
- Query → context retrieval → Claude flow

**Do NOT copy:**
- Component structure (god components)
- Database schema (19 tables → ~8 tables)
- State management patterns
- Accumulated complexity

## Key Reference Files

```
/Users/sean/Maestro4D/Maestro4D-1/apps/web-internal/
├── backend/app/services/
│   ├── context_tree_processor.py  # Three-pass pipeline logic
│   └── gemini_service.py          # Gemini prompts, extraction
├── backend/app/models.py          # Data structure patterns (not schema)
├── backend/app/routers/context.py # API endpoint patterns
├── components/PdfViewer.tsx       # Coordinate normalization
└── types/context.ts               # TypeScript interfaces
```

## Architecture Principles

1. **Normalized Coordinates:** All bounds in 0-1 range. Never store pixels.
2. **Three-Pass Pipeline:** Page analysis → cross-ref enrichment → discipline rollup
3. **Hybrid OCR:** PyMuPDF first, OCR fills gaps, IoU deduplication at 0.5
4. **Status State Machines:** Track processing through defined states
5. **Draft/Committed:** Pointers are drafts until explicitly committed

## Tech Stack Decisions

- **Frontend:** React + TypeScript + Tailwind + Vite
- **Backend:** FastAPI + Python
- **Database:** Supabase (Postgres) - NOT SQLite
- **Storage:** Supabase Storage for PDFs
- **PDF Rendering:** react-pdf (PDF.js wrapper)
- **AI:** Gemini for extraction, Claude for queries

## Database Schema (Target)

Keep it simple. ~8 tables instead of 19:

```sql
-- Supabase auth handles users
projects
project_files
context_pointers
page_contexts
discipline_contexts
queries
query_results
```

Row-level security policies handle access control.

## Component Architecture

Avoid god components. Keep concerns separated:

```
apps/web/src/
├── components/
│   ├── pdf/
│   │   ├── PdfViewer.tsx        # Just rendering
│   │   ├── BoxDrawer.tsx        # Just drawing logic
│   │   └── PointerOverlay.tsx   # Just pointer display
│   ├── context/
│   │   ├── ContextPanel.tsx     # Container only
│   │   ├── PointerList.tsx
│   │   ├── PageList.tsx
│   │   └── DisciplineList.tsx
│   └── query/
│       ├── QueryPanel.tsx
│       └── ResponseDisplay.tsx
├── hooks/
│   ├── usePointers.ts
│   ├── useProcessing.ts
│   └── useQuery.ts
└── lib/
    ├── coordinates.ts           # Normalization math
    ├── api.ts                   # Supabase client
    └── gemini.ts                # AI calls
```

## API Structure

```
services/api/app/
├── main.py
├── routers/
│   ├── projects.py
│   ├── files.py
│   ├── pointers.py
│   ├── processing.py            # Three-pass pipeline
│   └── queries.py
├── services/
│   ├── gemini.py                # Extraction
│   ├── ocr.py                   # Tesseract/PyMuPDF
│   └── context_processor.py     # Pass 1/2/3 orchestration
└── models/
    └── schemas.py               # Pydantic models
```

## Development Commands

```bash
# Frontend
cd apps/web
pnpm install
pnpm dev              # Port 5173

# Backend
cd services/api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Database
# Use Supabase dashboard or CLI
```

## Environment Variables

```bash
# Frontend (.env)
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
VITE_API_URL=http://localhost:8000

# Backend (.env)
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
GEMINI_API_KEY=
ANTHROPIC_API_KEY=
```

## Priority Order

Build in this order:

1. **Auth + Project CRUD** - Supabase OAuth, basic project management
2. **PDF Viewer** - Render pages, pan/zoom, page navigation
3. **Box Drawing** - Canvas overlay, coordinate capture, normalized storage
4. **Pointer Display** - Load/render pointers, click navigation
5. **OCR Pipeline** - Text extraction, storage in pointer
6. **Pass 1** - Page analysis, Gemini extraction
7. **Pass 2** - Cross-reference context
8. **Pass 3** - Discipline rollup
9. **Query Interface** - Text input, context retrieval, Claude response
10. **Polish** - Mode toggle, verification view, PDF export

## Common Patterns

### Coordinate Normalization
```typescript
// Always normalize on capture
const xNorm = (pixelX - canvasRect.left) / canvasRect.width;
const yNorm = (pixelY - canvasRect.top) / canvasRect.height;

// Always denormalize on render
const pixelX = xNorm * canvas.width;
const pixelY = yNorm * canvas.height;
```

### Supabase Queries
```typescript
// Use typed client
const { data, error } = await supabase
  .from('context_pointers')
  .select('*, page_context:page_contexts(*)')
  .eq('file_id', fileId);
```

### Processing Status Updates
```typescript
// Always update status atomically
await supabase
  .from('page_contexts')
  .update({ processing_status: 'pass1_processing' })
  .eq('id', pageId)
  .eq('processing_status', 'unprocessed');  // Optimistic lock
```

## Testing Approach

1. **Unit tests** for coordinate math, IoU calculation
2. **Integration tests** for processing pipeline
3. **E2E tests** for critical flows (upload → process → query)

## What Success Looks Like

- User uploads PDF in < 5 seconds
- Box drawing feels instant
- Processing shows live progress
- Query returns relevant context in < 3 seconds
- Entire app loads in < 2 seconds
