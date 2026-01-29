"""Services for AI and storage integrations.

This module re-exports all services from subfolders for backwards compatibility.
Services are organized into:
- core/: Orchestration and business logic (agent, processing_job, sheet_analyzer, conversation_memory)
- providers/: External API wrappers (gemini, claude, voyage, ocr, pdf_renderer)
- utils/: Internal utilities (storage, search, usage, detail_parser)
"""

# Core services
from app.services.core.agent import run_agent_query
from app.services.core.conversation_memory import fetch_conversation_history, trace_to_messages
from app.services.core.processing_job import (
    create_job_queue,
    emit_event,
    get_active_job_for_project,
    get_job_queue,
    pause_processing_job,
    process_project_pages,
    remove_job_queue,
    resume_processing_job,
    sse_event_generator,
    start_processing_job,
)
from app.services.core.sheet_analyzer import process_page, run_ocr, run_semantic_analysis

# Provider services
from app.services.providers.claude import generate_response, stream_response
from app.services.providers.gemini import (
    analyze_page_pass_1,
    analyze_pointer,
    run_agent_query as gemini_run_agent_query,
)
from app.services.providers.ocr import (
    crop_pdf_region,
    extract_full_page_text,
    extract_text_with_positions,
)
from app.services.providers.pdf_renderer import (
    get_pdf_page_count,
    pdf_page_to_image,
)
from app.services.providers.voyage import embed_pointer, embed_text

# Utility services
from app.services.utils.detail_parser import (
    extract_sheet_info,
    parse_context_markdown,
    parse_detail_section,
)
from app.services.utils.search import search_pointers
from app.services.utils.storage import (
    delete_file,
    download_file,
    get_download_url,
    get_public_url,
    upload_page_image,
    upload_pdf,
    upload_snapshot,
)
from app.services.utils.usage import UsageService

# Keep tools at top level
from app.services.tools import (
    TOOL_REGISTRY,
    get_discipline_overview,
    get_page_context,
    get_pointer,
    get_project_structure_summary,
    get_references_to_page,
    invalidate_project_structure_cache,
    list_project_pages,
    resolve_highlights,
    search_pages,
    select_pages,
    select_pointers,
)

__all__ = [
    # Core
    "run_agent_query",
    "fetch_conversation_history",
    "trace_to_messages",
    "create_job_queue",
    "emit_event",
    "get_active_job_for_project",
    "get_job_queue",
    "pause_processing_job",
    "process_project_pages",
    "remove_job_queue",
    "resume_processing_job",
    "sse_event_generator",
    "start_processing_job",
    "process_page",
    "run_ocr",
    "run_semantic_analysis",
    # Providers
    "generate_response",
    "stream_response",
    "analyze_page_pass_1",
    "analyze_pointer",
    "gemini_run_agent_query",
    "crop_pdf_region",
    "extract_full_page_text",
    "extract_text_with_positions",
    "get_pdf_page_count",
    "pdf_page_to_image",
    "embed_pointer",
    "embed_text",
    # Utils
    "extract_sheet_info",
    "parse_context_markdown",
    "parse_detail_section",
    "search_pointers",
    "delete_file",
    "download_file",
    "get_download_url",
    "get_public_url",
    "upload_page_image",
    "upload_pdf",
    "upload_snapshot",
    "UsageService",
    # Tools
    "TOOL_REGISTRY",
    "get_discipline_overview",
    "get_page_context",
    "get_pointer",
    "get_project_structure_summary",
    "get_references_to_page",
    "invalidate_project_structure_cache",
    "list_project_pages",
    "resolve_highlights",
    "search_pages",
    "select_pages",
    "select_pointers",
]
