# Backend Services

Organized into three layers: core business logic, external providers, and internal utilities.

## core/ — Orchestration Layer

Business logic that coordinates between providers and database.

### agent.py
Query agent for navigating construction plan graph.
- Uses Gemini structured output for single-shot queries (fast path)
- Tool definitions: `search_pointers`, `search_pages`, `select_pointers`
- Streams responses via SSE with thinking, tool calls, and final answer
- `run_agent_query()`: Main entry point for Maestro Mode queries

### processing_job.py
Background job system for sheet-analyzer pipeline.
- Status flow: `pending` → `processing` → `completed/failed/paused`
- `start_processing_job()`: Kicks off page-by-page processing
- `process_project_pages()`: Iterates through pages calling sheet_analyzer
- `pause_processing_job()` / `resume_processing_job()`: Job control
- `sse_event_generator()`: Streams progress events to frontend

### sheet_analyzer.py
OCR + Semantic Classification for construction sheets.

Pipeline:
1. Tiled EasyOCR for bbox detection (handles large images)
2. Geometric bbox stitching across tile boundaries
3. Gemini text labeling (handles vertical/rotated text)
4. Quadrant-based semantic classification (region_type, role)
5. Context markdown generation

Key functions:
- `process_page()`: Full pipeline for one page
- `run_ocr()`: EasyOCR with tiling
- `run_semantic_analysis()`: Gemini classification

### conversation_memory.py
Session context management for multi-turn queries.
- `fetch_conversation_history()`: Get previous turns for context
- `trace_to_messages()`: Convert agent trace to message format

## providers/ — External API Wrappers

Thin wrappers around third-party services.

### gemini.py
Google Gemini integration for visual analysis.
- `analyze_page_pass_1()`: Initial page classification
- `analyze_pointer()`: Detail/callout analysis
- `run_agent_query()`: Structured output for queries

### claude.py
Anthropic Claude integration.
- `generate_response()`: Single response generation
- `stream_response()`: Streaming response

### voyage.py
Voyage AI embeddings for semantic search.
- `embed_text()`: Embed query text
- `embed_pointer()`: Embed pointer content

### ocr.py
OCR utilities using EasyOCR.
- `extract_text_with_positions()`: Get text with bboxes
- `extract_full_page_text()`: Plain text extraction
- `crop_pdf_region()`: Extract region from PDF

### pdf_renderer.py
PDF to image conversion using pdf2image.
- `pdf_page_to_image()`: Render single page
- `get_pdf_page_count()`: Count pages in PDF
- `crop_pdf_region()`: Extract cropped region

## utils/ — Internal Utilities

Helper functions used across services.

### storage.py
Supabase Storage operations.
- `upload_pdf()`, `upload_page_image()`, `upload_snapshot()`
- `download_file()`, `delete_file()`
- `get_public_url()`, `get_download_url()`

### search.py
Semantic search using Voyage embeddings.
- `search_pointers()`: Find relevant pointers by query

### usage.py
API usage tracking.
- `UsageService`: Track token usage across providers

### detail_parser.py
Parse Gemini's context markdown output.
- `parse_context_markdown()`: Extract structured data
- `extract_sheet_info()`: Pull sheet metadata
- `parse_detail_section()`: Parse detail annotations

## Data Flows

### Query Flow (Maestro Mode)
```
POST /query
    │
    ▼
agent.run_agent_query()
    │
    ├─→ search_pointers() ─→ voyage.embed_text() ─→ vector search
    │
    ├─→ search_pages() ─→ database query
    │
    └─→ SSE stream: thinking → tool_call → tool_result → response
```

### Processing Flow (Brain Mode)
```
POST /projects/{id}/pages (upload)
    │
    ▼
processing_job.start_processing_job()
    │
    ▼
For each page:
    sheet_analyzer.process_page()
        │
        ├─→ pdf_renderer.pdf_page_to_image()
        ├─→ ocr.extract_text_with_positions() (tiled)
        ├─→ gemini.analyze_page_pass_1()
        └─→ voyage.embed_pointer() (for each pointer)
    │
    ▼
SSE events: page_started → page_completed → job_completed
```
