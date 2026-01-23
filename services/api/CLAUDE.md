# Backend CLAUDE.md

FastAPI + Python. Deployed to Railway.

## Architecture

```
app/
├── main.py              # FastAPI app, CORS, router mounting
├── config.py            # Environment variables (Settings class)
├── routers/
│   ├── projects.py      # Project CRUD, file upload, Google Drive import
│   ├── processing.py    # Brain Mode pipeline (tiled OCR, Gemini analysis)
│   ├── queries.py       # Query endpoint with SSE streaming
│   ├── pointers.py      # Context pointer CRUD
│   ├── pages.py         # Page context retrieval
│   ├── disciplines.py   # Discipline context retrieval
│   ├── conversations.py # Conversation/session management
│   └── health.py        # Health check endpoint
├── services/
│   ├── agent.py         # Agentic query handler (Claude + tools)
│   ├── sheet_analyzer.py # Tiled OCR + Gemini quadrant analysis
│   ├── processing_job.py # Background processing orchestration
│   ├── tools.py         # Agent tools (search, navigate, etc.)
│   ├── gemini.py        # Gemini API client
│   ├── claude.py        # Claude API client
│   ├── ocr.py           # EasyOCR wrapper
│   ├── pdf_renderer.py  # PyMuPDF page rendering
│   ├── storage.py       # Supabase Storage operations
│   ├── search.py        # Vector search (Voyage embeddings)
│   ├── voyage.py        # Voyage AI embedding client
│   ├── usage.py         # Token/cost tracking
│   └── conversation_memory.py # Session context
├── database/
│   └── supabase.py      # Supabase client initialization
├── models/              # SQLAlchemy models (if used)
├── schemas/             # Pydantic request/response schemas
├── auth/                # JWT verification, user extraction
├── dependencies/        # FastAPI dependencies
└── utils/               # Helpers
```

## Key Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /projects/{id}/files/upload` | Upload PDF to Supabase Storage |
| `POST /projects/{id}/process` | Trigger Brain Mode processing |
| `GET /projects/{id}/process/status` | SSE stream of processing progress |
| `POST /projects/{id}/query` | SSE stream of agent response |
| `GET /conversations/{id}/messages` | Conversation history |

## Processing Pipeline (Brain Mode)

Current architecture (being rearchitected):

1. **PDF Upload** → Store in Supabase Storage
2. **Tiled OCR** → Split page into ~15 tiles, EasyOCR for bounding boxes
3. **Stitch** → Combine bounding boxes across tiles
4. **PNG Extraction** → Crop each text span to PNG
5. **Quadrant Analysis** → Gemini processes 4 quadrants with text context
6. **Classification** → Text spans classified (detail title, measurement, note, etc.)
7. **Master Markdown** → Full page context document

**Target:** All processing at upload time. Query becomes pure RAG retrieval.

## Agent Architecture

`services/agent.py` handles queries:

1. Receive query + project context
2. Retrieve relevant pages/pointers via vector search
3. Claude generates response with tool access
4. Stream response via SSE

**Tools available to agent:**
- `search_pages` — Vector search across page contexts
- `get_page_detail` — Full context for specific page
- `navigate_to_page` — Return page reference to frontend

## Database Schema

~8 tables in Supabase (Postgres):

```sql
projects           -- User projects
project_files      -- PDFs and folders within projects
context_pointers   -- User-drawn boxes with AI analysis
page_contexts      -- Page-level analysis (Pass 1 & 2)
discipline_contexts -- Discipline rollups (Pass 3)
queries            -- Query history
usage_events       -- Token/cost tracking
conversations      -- Chat sessions
```

See `/services/api/supabase/` for migrations.

## Environment Variables

```bash
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
GEMINI_API_KEY=
ANTHROPIC_API_KEY=
VOYAGE_API_KEY=
ENVIRONMENT=development
```

## Development

```bash
cd services/api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Current State

**Working:**
- File upload and storage
- Basic processing pipeline
- Query streaming with SSE
- Conversation sessions

**Broken/Blocked:**
- Agent response times (~3 min, need <10 sec)
- Processing not optimized for front-loading

**Current Focus:**
- Rearchitecting to pure RAG
- Front-load all processing at upload
- Eliminate query-time complexity
- Automated context pointer creation

## Key Algorithms

- **Coordinate Normalization:** `norm = (pixel - offset) / dimension`
- **IoU Deduplication:** Threshold 0.5 for overlapping text spans
- **150 DPI Capture:** `scale = 150 / 72 ≈ 2.08` for snapshots
- **Tiled OCR:** ~15 tiles per page to handle large PDFs
