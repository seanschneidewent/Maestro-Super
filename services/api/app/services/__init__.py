"""Services for AI and storage integrations.

Services are organized into subfolders:
- core/: Orchestration and business logic (agent, processing_job, sheet_analyzer, conversation_memory)
- providers/: External API wrappers (gemini, claude, voyage, ocr, pdf_renderer)
- utils/: Internal utilities (storage, search, usage, detail_parser)

Backwards compatibility:
    Stub files at the top level (e.g., services/gemini.py) re-export from subfolders,
    so existing imports like `from app.services.gemini import ...` continue to work.

    This avoids eager loading of heavy dependencies (EasyOCR, pdf2image, etc.)
    when only a subset of services are needed.
"""
