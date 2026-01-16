# CLAUDE.md - Instructions for Claude Code

## Session Initialization

**At the start of EVERY new session, run these commands:**

```bash
cd claude-memory && ./scripts/sync-memory.sh && cat CONTEXT.md
```

This syncs your persistent memory from Supabase and loads the current context. Do this before any other work.

---

## Project Overview

Maestro Super is a clean rewrite of a construction plan analysis system. One app, two modes: Setup (draw boxes, process, commit) and Use (query plans, get AI walkthroughs).

**Business Model:** Free to start, usage-based pricing. First project + 10 chats free. After that, pay per AI usage (API cost + 50% margin).

**Target Market:** Superintendents in Texas. Start local, grow from real relationships.

## Architecture

Read `docs/ARCHITECTURE.md` for the complete system design (normalized coordinates, three-pass pipeline, data structures).

### Deployment Stack (Simple, Texas-Focused)

Start simple. Scale when you have 500 users and know what's actually slow.

| Layer | Choice | Why |
|-------|--------|-----|
| Frontend | Vercel | Deploy with git push, free tier is plenty |
| Backend | Railway | Single server, US region, $5-20/month, scales when needed |
| Database | Supabase (Postgres) | Auth + Database + Storage in one platform |
| PDF Storage | Supabase Storage | Good enough for now, migrate to R2 if egress costs matter |
| AI | Gemini (extraction), Claude (queries) | |

**What we're NOT doing yet:**
- Job queues (process PDFs synchronously with good loading states)
- Edge functions / multi-region
- Connection pooling complexity
- Microservices

When things creak at 500 users, optimize the real bottleneck.

### Database Schema (Simplified)

~8 tables instead of the 19-table mess from the prototype:

```sql
-- Supabase Auth handles users automatically

-- Projects
CREATE TABLE projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  status TEXT DEFAULT 'setup', -- 'setup' | 'processing' | 'ready'
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Files within projects
CREATE TABLE project_files (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  storage_path TEXT NOT NULL, -- Supabase Storage path
  file_type TEXT NOT NULL, -- 'pdf' | 'image'
  page_count INTEGER,
  parent_id UUID REFERENCES project_files(id), -- For folder hierarchy
  is_folder BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Context pointers (user-drawn boxes with AI analysis)
CREATE TABLE context_pointers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  file_id UUID REFERENCES project_files(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL,
  
  -- Normalized bounds (0-1 coordinate space)
  x_norm FLOAT NOT NULL,
  y_norm FLOAT NOT NULL,
  w_norm FLOAT NOT NULL,
  h_norm FLOAT NOT NULL,
  
  -- Content
  title TEXT,
  description TEXT,
  snapshot_url TEXT, -- Storage path for 150 DPI crop
  
  -- AI Analysis (from Gemini)
  ai_technical_description TEXT,
  ai_trade_category TEXT, -- 'ELEC', 'MECH', 'PLMB', etc.
  ai_elements JSONB, -- [{name, type, details}]
  ai_measurements JSONB,
  
  -- Extracted text (hybrid OCR)
  text_content JSONB,
  
  -- Status
  status TEXT DEFAULT 'generating', -- 'generating' | 'complete' | 'error'
  committed_at TIMESTAMPTZ, -- null = draft, timestamp = published
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Page-level context (Pass 1 & 2 output)
CREATE TABLE page_contexts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  file_id UUID REFERENCES project_files(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL,
  
  sheet_number TEXT, -- "E-2.1"
  discipline_code TEXT, -- A, S, M, E, P, FP, C, L, G
  
  -- Pass 1 output
  context_summary TEXT,
  pass1_output JSONB,
  
  -- Pass 2 output  
  pass2_output JSONB,
  inbound_references JSONB,
  
  -- Processing state
  processing_status TEXT DEFAULT 'unprocessed',
  retry_count INTEGER DEFAULT 0,
  
  UNIQUE(file_id, page_number)
);

-- Discipline-level context (Pass 3 output)
CREATE TABLE discipline_contexts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  code TEXT NOT NULL, -- A, S, M, E, P, FP, C, L, G
  name TEXT NOT NULL,
  
  context_description TEXT,
  key_contents JSONB,
  connections JSONB,
  
  processing_status TEXT DEFAULT 'waiting',
  
  UNIQUE(project_id, code)
);

-- Query history
CREATE TABLE queries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  query_text TEXT NOT NULL,
  response_text TEXT,
  referenced_pointers JSONB, -- [{pointer_id, relevance_score}]
  tokens_used INTEGER,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Usage tracking (for billing)
CREATE TABLE usage_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL, -- 'gemini_extraction' | 'claude_query' | 'ocr_page'
  tokens_input INTEGER,
  tokens_output INTEGER,
  cost_cents INTEGER, -- Actual API cost in cents
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Row Level Security (every table)
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE context_pointers ENABLE ROW LEVEL SECURITY;
ALTER TABLE page_contexts ENABLE ROW LEVEL SECURITY;
ALTER TABLE discipline_contexts ENABLE ROW LEVEL SECURITY;
ALTER TABLE queries ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;

-- RLS Policies (users only see their own data)
CREATE POLICY "Users see own projects" ON projects
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users see own files" ON project_files
  FOR ALL USING (
    project_id IN (SELECT id FROM projects WHERE user_id = auth.uid())
  );

-- Similar policies for other tables...
```

## Tech Stack

- **Frontend:** React + TypeScript + Tailwind + Vite
- **Backend:** FastAPI + Python
- **Database:** Supabase (Postgres)
- **Storage:** Supabase Storage
- **PDF Rendering:** react-pdf (PDF.js wrapper)
- **PDF Processing:** PyMuPDF + Tesseract OCR
- **AI:** Gemini for extraction, Claude for queries

## Project Structure

```
maestro-super/
├── apps/
│   └── web/                 # React frontend (Vercel)
├── services/
│   └── api/                 # FastAPI backend (Railway)
│       ├── app/
│       │   ├── main.py
│       │   ├── config.py
│       │   ├── routers/
│       │   │   ├── projects.py
│       │   │   ├── files.py
│       │   │   ├── pointers.py
│       │   │   ├── processing.py
│       │   │   └── queries.py
│       │   ├── services/
│       │   │   ├── gemini.py
│       │   │   ├── claude.py
│       │   │   ├── ocr.py
│       │   │   └── context_processor.py
│       │   └── models/
│       │       └── schemas.py
│       └── requirements.txt
├── docs/
│   ├── ARCHITECTURE.md      # Complete system design
│   └── PROMPTS.md           # AI prompt templates
└── CLAUDE.md                # This file
```

## Reference Implementation

The prototype lives at: `/Users/sean/Maestro4D/Maestro4D-1/apps/web-internal/`

**When to reference:**
- Exact Gemini prompt text for the three-pass pipeline
- Specific coordinate math edge cases
- OCR integration patterns
- Query → context retrieval → Claude flow

**Do NOT copy:**
- Component structure (god components)
- Database schema (19 tables → 8 tables)
- State management patterns
- Accumulated complexity

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

## Development Commands

```bash
# Frontend
cd apps/web
pnpm install
pnpm dev              # Port 3000

# Backend
cd services/api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Build Priority

1. **Auth** - Supabase OAuth (Google), basic session handling
2. **Project CRUD** - Create project, upload PDFs to Supabase Storage
3. **PDF Viewer** - Render pages, pan/zoom, page navigation
4. **Box Drawing** - Canvas overlay, normalized coordinate capture, save to Postgres
5. **Pointer Display** - Load/render existing pointers, click to navigate
6. **OCR Pipeline** - PyMuPDF + Tesseract, hybrid extraction, store in pointer
7. **Pass 1** - Page analysis with Gemini
8. **Pass 2** - Cross-reference context enrichment
9. **Pass 3** - Discipline rollup
10. **Query Interface** - Text input, context retrieval, Claude streaming response
11. **Usage Tracking** - Log every AI call with token counts and costs
12. **Polish** - Mode toggle, verification view, export to PDF

## Key Algorithms (from ARCHITECTURE.md)

1. **Coordinate Normalization:** `norm = (pixel - offset) / dimension`
2. **IoU Deduplication:** Threshold 0.5 for hybrid text extraction
3. **150 DPI Capture:** `scale = 150 / 72 ≈ 2.08`
4. **Zoom-to-Bounds:** `zoom = viewport / (bounds * 1.4)`, clamped 1x-4x
5. **Reference Inversion:** outbound refs → inbound refs after Pass 1

## What Success Looks Like

- User uploads PDF in < 5 seconds
- Box drawing feels instant
- Processing shows live progress
- Query returns relevant context in < 3 seconds
- Entire app loads in < 2 seconds
- You can see exactly what every user is doing in logs
- When something breaks, you know why within 5 minutes
