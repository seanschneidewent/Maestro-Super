"""Pydantic schemas for API request/response validation."""

from app.schemas.common import PaginatedResponse
from app.schemas.discipline import (
    DisciplineCreate,
    DisciplineResponse,
    DisciplineUpdate,
)
from app.schemas.page import (
    PageCreate,
    PageResponse,
    PageUpdate,
)
from app.schemas.pointer import (
    BoundingBox,
    PointerCreate,
    PointerResponse,
    PointerUpdate,
)
from app.schemas.pointer_reference import (
    PointerReferenceCreate,
    PointerReferenceResponse,
)
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.schemas.query import QueryCreate, QueryResponse, QueryUpdate
from app.schemas.usage_event import UsageEventCreate, UsageEventResponse

__all__ = [
    # Common
    "PaginatedResponse",
    # Project
    "ProjectCreate",
    "ProjectUpdate",
    "ProjectResponse",
    # Discipline
    "DisciplineCreate",
    "DisciplineUpdate",
    "DisciplineResponse",
    # Page
    "PageCreate",
    "PageUpdate",
    "PageResponse",
    # Pointer
    "BoundingBox",
    "PointerCreate",
    "PointerUpdate",
    "PointerResponse",
    # PointerReference
    "PointerReferenceCreate",
    "PointerReferenceResponse",
    # Query
    "QueryCreate",
    "QueryUpdate",
    "QueryResponse",
    # UsageEvent
    "UsageEventCreate",
    "UsageEventResponse",
]
