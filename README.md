# Maestro Super

AI-powered construction plan analysis for superintendents. One app for setup and use.

## What This Is

Superintendents upload construction PDFs, draw boxes around important regions, and the system extracts context using AI. Then they query their plans using natural language and get precise answers with sheet references.

## Architecture

**Two Modes, One App:**
- **Setup Mode** - Upload PDFs, draw context pointers, process with AI, verify, commit
- **Use Mode** - Query plans via text/voice, get walkthrough responses, export to PDF

**Core Flow:**
1. Auth (Supabase OAuth)
2. Create project → upload PDFs
3. PDF viewer with box drawing (normalized 0-1 coordinates)
4. Per-box AI processing (Tesseract OCR → Gemini extraction)
5. Three-pass context enrichment (page → cross-reference → discipline rollup)
6. Verification view → commit
7. Query interface → Claude with context retrieval
8. Export walkthrough to PDF

## Tech Stack

- **Frontend:** React + TypeScript + Tailwind
- **Backend:** FastAPI + Python
- **Database:** Supabase (Postgres)
- **Storage:** Supabase Storage / R2
- **AI:** Gemini (extraction), Claude (queries)
- **PDF:** react-pdf, PDF.js, PyMuPDF

## Project Structure

```
maestro-super/
├── apps/
│   └── web/                 # React frontend
├── services/
│   └── api/                 # FastAPI backend
├── docs/
│   ├── ARCHITECTURE.md      # Complete system design
│   └── PROMPTS.md           # AI prompt templates
└── CLAUDE.md                # Instructions for Claude Code
```

## Development

```bash
# Frontend
cd apps/web && pnpm install && pnpm dev

# Backend
cd services/api && pip install -r requirements.txt && uvicorn app.main:app --reload
```

## Reference Implementation

The logic for this system was prototyped in a separate codebase. When implementing complex features, reference:
- `/path/to/Maestro4D-1/apps/web-internal/` for existing patterns

Key files worth referencing:
- `backend/app/services/context_tree_processor.py` - Three-pass AI pipeline
- `backend/app/services/gemini_service.py` - Gemini prompts and extraction
- `components/PdfViewer.tsx` - Coordinate normalization patterns
- `backend/app/models.py` - Data structure patterns (not the schema itself)
