"""In-memory session types for Maestro V3."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID


@dataclass
class WorkspaceState:
    """Workspace state tracked in memory and checkpointed to the database."""

    displayed_pages: list[str] = field(default_factory=list)
    highlighted_pointers: list[str] = field(default_factory=list)
    pinned_pages: list[str] = field(default_factory=list)


@dataclass
class LiveSession:
    """In-memory session. The hot layer."""

    session_id: UUID
    project_id: UUID
    user_id: str
    session_type: str  # 'workspace' | 'telegram'

    # Conversation state — these ARE the context windows
    maestro_messages: list[dict] = field(default_factory=list)
    learning_messages: list[dict] = field(default_factory=list)

    # Workspace (None for telegram)
    workspace_state: Optional[WorkspaceState] = None

    # Learning queue — interactions waiting for Learning to process
    learning_queue: asyncio.Queue = field(default_factory=asyncio.Queue)

    # Event bus - forwards async Learning events to SSE clients
    event_bus: asyncio.Queue = field(default_factory=asyncio.Queue)

    # Background Learning worker task
    learning_task: asyncio.Task | None = None
    learning_task_loop: asyncio.AbstractEventLoop | None = None

    # Metadata
    dirty: bool = False
    last_active: float = 0.0
