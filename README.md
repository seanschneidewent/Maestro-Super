# Maestro Super

AI-powered construction plan analysis for superintendents. Draw boxes, extract context, query your plans.

## What This Is

Superintendents upload construction PDFs, draw boxes around important regions, and the system extracts context using AI. Then they query their plans using natural language and get precise answers with sheet references and visual walkthroughs.

**One app. Two modes.**
- **Setup Mode** - Upload PDFs, draw context pointers, process with AI, verify, commit
- **Use Mode** - Query plans via text/voice, get walkthrough responses, export to PDF

## Business Model

Free to start. Pay for what you use.

- **Free tier:** First project + 10 AI queries
- **After that:** Pay per AI usage (our cost + 50%)
- **No subscriptions.** No per-seat licensing. No enterprise sales calls.

Superintendents already pay for 47 tools. We're not adding another monthly bill they have to track.

## Tech Stack

Intentionally simple. Scales when we need it to.

| Layer | Choice | Cost |
|-------|--------|------|
| Frontend | Vercel | Free tier |
| Backend | Railway | ~$5-20/month |
| Database + Auth + Storage | Supabase | Free tier to start |
| AI | Gemini + Claude | Usage-based |

**Not using (yet):**
- Job queues
- Edge functions
- Multi-region deployment
- Kubernetes or anything fancy

When we have 500 active users and things start creaking, we'll know exactly what's slow and fix that specific thing.

## Core Flow

1. **Auth** → Sign in with Google (Supabase Auth)
2. **Create project** → Upload construction PDFs
3. **Draw boxes** → Highlight important regions on each page
4. **AI processing** → OCR + Gemini extracts context from each box
5. **Verify** → Review all extracted data
6. **Commit** → Lock project, ready for queries
7. **Query** → Ask questions in natural language
8. **Get answers** → Claude responds with sheet references and visual walkthroughs
9. **Export** → Generate PDF walkthrough to share

## Architecture

The system is built on a few key ideas:

**Normalized Coordinates (0-1 space)**
Every point and bounding box lives in a 0-1 coordinate space. This makes everything zoom-agnostic, resolution-agnostic, and portable.

**Three-Pass Context Pipeline**
1. Pass 1: Analyze each page independently, identify cross-references
2. Pass 2: Enrich references with context from target pages  
3. Pass 3: Roll up into discipline-level summaries

**Hybrid Text Extraction**
PyMuPDF extracts native PDF text. Tesseract OCR catches rasterized text. IoU-based deduplication at 0.5 threshold merges them cleanly.

See `docs/ARCHITECTURE.md` for the complete technical specification.

## Project Structure

```
maestro-super/
├── apps/
│   └── web/                 # React frontend
├── services/
│   └── api/                 # FastAPI backend
├── docs/
│   ├── ARCHITECTURE.md      # Technical deep-dive
│   └── PROMPTS.md           # AI prompt templates
├── CLAUDE.md                # Instructions for Claude Code
└── README.md                # This file
```

## Development

```bash
# Frontend
cd apps/web
pnpm install
pnpm dev

# Backend
cd services/api
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Local Development Setup

Full local dev with a Docker Postgres, hot-reload backend, and Vite frontend.

### Prerequisites

- **Docker Desktop** (Windows) — [install](https://docs.docker.com/desktop/install/windows-install/)
- **Python 3.13+** with venv at `services/api/venv/`
- **Node.js v22+** with pnpm
- **PostgreSQL 16 client tools** (for `pg_dump`/`psql`) — [install](https://www.postgresql.org/download/windows/)

### Quick Start

```powershell
# One-command startup (Docker, Postgres, migrations, backend, frontend)
.\scripts\dev.ps1

# Seed production data into local Postgres (first time only)
.\scripts\seed-local-db.ps1
```

### Manual Steps

```powershell
# 1. Start Postgres
docker compose up -d

# 2. Run migrations
cd services\api
.\venv\Scripts\Activate.ps1
alembic upgrade head

# 3. Start backend (new terminal)
uvicorn app.main:app --reload --port 8000

# 4. Start frontend (new terminal)
cd apps\web
pnpm dev
```

### Environment Files

Local overrides go in `.env.local` (gitignored):

| File | Purpose |
|------|---------|
| `services/api/.env.local` | DB credentials, DEV_USER_ID, Supabase keys, AI keys |
| `apps/web/.env.local` | `VITE_API_URL=http://localhost:8000`, Supabase URL/key |

See `services/api/.env.example` for all available variables.

### Debug Traces

When `DEV_USER_ID` is set, every query writes a debug summary to:

```
services/api/debug/last-query.json
```

Last 5 queries are kept as `last-query-1.json` through `last-query-5.json`.

### Data Seeding

```powershell
# Dump production data into local Postgres
.\scripts\seed-local-db.ps1

# If pg_dump is not on PATH, use Docker-based dump:
.\scripts\seed-local-db.ps1 -UsePgDocker

# Reset database completely (wipe volume, re-init, re-migrate)
docker compose down -v
docker compose up -d
# Wait for healthy, then:
cd services\api && .\venv\Scripts\python.exe -m alembic upgrade head
.\scripts\seed-local-db.ps1
```

## Environment Variables

```bash
# Supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_KEY=

# AI
GEMINI_API_KEY=
ANTHROPIC_API_KEY=
```

## Reference Implementation

Core logic was prototyped in a separate codebase. When implementing complex features, reference:

```
/path/to/Maestro4D-1/apps/web-internal/
├── backend/app/services/context_tree_processor.py  # Three-pass pipeline
├── backend/app/services/gemini_service.py          # Gemini prompts
└── components/PdfViewer.tsx                        # Coordinate math
```

Pull the logic. Leave the complexity.

## Status

Early development. Starting with Texas superintendents, growing from real relationships.
