from enum import Enum


class ProjectStatus(str, Enum):
    """Project lifecycle status."""

    SETUP = "setup"
    PROCESSING = "processing"
    READY = "ready"


class PointerStatus(str, Enum):
    """Context pointer processing status."""

    GENERATING = "generating"
    COMPLETE = "complete"
    ERROR = "error"


class ProcessingStatus(str, Enum):
    """Page context processing state machine."""

    UNPROCESSED = "unprocessed"
    PASS1_PROCESSING = "pass1_processing"
    PASS1_COMPLETE = "pass1_complete"
    PASS2_PROCESSING = "pass2_processing"
    PASS2_COMPLETE = "pass2_complete"


class DisciplineStatus(str, Enum):
    """Discipline context processing status."""

    WAITING = "waiting"
    READY = "ready"
    PROCESSING = "processing"
    COMPLETE = "complete"


class FileType(str, Enum):
    """Project file types."""

    PDF = "pdf"
    IMAGE = "image"


class EventType(str, Enum):
    """Usage event types for billing."""

    GEMINI_EXTRACTION = "gemini_extraction"
    CLAUDE_QUERY = "claude_query"
    OCR_PAGE = "ocr_page"
