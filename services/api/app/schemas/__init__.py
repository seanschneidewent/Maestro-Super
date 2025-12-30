"""Pydantic schemas for API request/response validation."""

from app.schemas.common import Bounds, PaginatedResponse
from app.schemas.context_pointer import (
    ContextPointerCreate,
    ContextPointerResponse,
    ContextPointerUpdate,
)
from app.schemas.discipline_context import (
    DisciplineContextCreate,
    DisciplineContextResponse,
    DisciplineContextUpdate,
)
from app.schemas.page_context import (
    PageContextCreate,
    PageContextResponse,
    PageContextUpdate,
)
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.schemas.project_file import (
    ProjectFileCreate,
    ProjectFileResponse,
    ProjectFileTreeResponse,
    ProjectFileUpdate,
)
from app.schemas.query import QueryCreate, QueryResponse, QueryUpdate
from app.schemas.usage_event import UsageEventCreate, UsageEventResponse

__all__ = [
    # Common
    "Bounds",
    "PaginatedResponse",
    # Project
    "ProjectCreate",
    "ProjectUpdate",
    "ProjectResponse",
    # ProjectFile
    "ProjectFileCreate",
    "ProjectFileUpdate",
    "ProjectFileResponse",
    "ProjectFileTreeResponse",
    # ContextPointer
    "ContextPointerCreate",
    "ContextPointerUpdate",
    "ContextPointerResponse",
    # PageContext
    "PageContextCreate",
    "PageContextUpdate",
    "PageContextResponse",
    # DisciplineContext
    "DisciplineContextCreate",
    "DisciplineContextUpdate",
    "DisciplineContextResponse",
    # Query
    "QueryCreate",
    "QueryUpdate",
    "QueryResponse",
    # UsageEvent
    "UsageEventCreate",
    "UsageEventResponse",
]
