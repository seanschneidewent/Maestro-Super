"""V3 session endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import User
from app.database.session import get_db
from app.models.experience_file import ExperienceFile
from app.models.project import Project
from app.models.session import MaestroSession
from app.services.v3.benchmark_report import (
    generate_evolution_report,
    get_dimension_summary,
    get_recent_corrections,
)
from app.services.v3.maestro_agent import run_maestro_turn
from app.services.v3.session_manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v3", tags=["v3"])


def _drain_event_bus(session) -> list[dict]:
    events: list[dict] = []
    if not getattr(session, "event_bus", None):
        return events
    while True:
        try:
            events.append(session.event_bus.get_nowait())
        except asyncio.QueueEmpty:
            break
        except Exception:
            break
    return events


def _last_message_preview(messages: list[dict]) -> str | None:
    for message in reversed(messages or []):
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not content:
            continue
        text = str(content).strip()
        if not text:
            continue
        return text[:140]
    return None


def _normalize_panels(panels: dict | None) -> dict[str, str]:
    panels = panels or {}
    return {
        "workspace_assembly": str(panels.get("workspace_assembly") or ""),
        "learning": str(panels.get("learning") or ""),
        "knowledge_update": str(panels.get("knowledge_update") or ""),
    }


def _build_turn_history(messages: list[dict]) -> list[dict]:
    turns: list[dict] = []
    current_user: str | None = None
    current_turn = 0

    for message in messages or []:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role == "user":
            current_user = str(message.get("content") or "")
            try:
                current_turn = int(message.get("turn_number") or (current_turn + 1))
            except (TypeError, ValueError):
                current_turn = current_turn + 1
        elif role == "assistant":
            if current_user is None:
                continue
            try:
                turn_number = int(message.get("turn_number") or current_turn or (len(turns) + 1))
            except (TypeError, ValueError):
                turn_number = current_turn or (len(turns) + 1)
            turns.append(
                {
                    "turn_number": turn_number,
                    "user": current_user,
                    "response": str(message.get("content") or ""),
                    "panels": _normalize_panels(message.get("panels")),
                }
            )
            current_user = None

    if current_user is not None:
        turns.append(
            {
                "turn_number": current_turn or (len(turns) + 1),
                "user": current_user,
                "response": "",
                "panels": _normalize_panels(None),
            }
        )

    return turns


class CreateSessionRequest(BaseModel):
    project_id: UUID
    session_type: Literal["workspace", "telegram"]
    workspace_name: Optional[str] = None


class QueryRequest(BaseModel):
    message: str


class RenameSessionRequest(BaseModel):
    workspace_name: str


def _verify_project(project_id: UUID, user: User, db: Session) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == str(project_id))
        .filter(Project.user_id == user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/sessions")
def create_session(
    data: CreateSessionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _verify_project(data.project_id, user, db)
    session = SessionManager.instance().create_session(
        project_id=data.project_id,
        user_id=user.id,
        session_type=data.session_type,
        workspace_name=data.workspace_name,
        db=db,
    )
    return {
        "session_id": str(session.session_id),
        "session_type": session.session_type,
        "workspace_name": session.workspace_name,
        "workspace_state": (
            {
                "displayed_pages": session.workspace_state.displayed_pages,
                "highlighted_pointers": session.workspace_state.highlighted_pointers,
                "pinned_pages": session.workspace_state.pinned_pages,
            }
            if session.workspace_state
            else None
        ),
    }


@router.get("/sessions")
def list_sessions(
    project_id: UUID,
    session_type: Optional[Literal["workspace", "telegram"]] = None,
    status: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    _verify_project(project_id, user, db)
    status_list = None
    if status:
        status_list = [value.strip() for value in status.split(",") if value.strip()]
    sessions = SessionManager.instance().list_sessions(
        project_id=project_id,
        session_type=session_type,
        status=status_list,
        db=db,
    )
    return [
        {
            "session_id": row.id,
            "session_type": row.session_type,
            "workspace_name": row.workspace_name,
            "status": row.status,
            "last_active_at": row.last_active_at.isoformat() if row.last_active_at else None,
            "last_message_preview": _last_message_preview(row.maestro_messages or []),
        }
        for row in sessions
    ]


@router.get("/sessions/{session_id}")
def get_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    session = SessionManager.instance().get_session(session_id, db)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return {
        "session_id": str(session.session_id),
        "session_type": session.session_type,
        "workspace_name": session.workspace_name,
        "status": "active",
        "maestro_messages": session.maestro_messages,
        "workspace_state": (
            {
                "displayed_pages": session.workspace_state.displayed_pages,
                "highlighted_pointers": session.workspace_state.highlighted_pointers,
                "pinned_pages": session.workspace_state.pinned_pages,
            }
            if session.workspace_state
            else None
        ),
    }


@router.patch("/sessions/{session_id}")
def rename_session(
    session_id: UUID,
    data: RenameSessionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    session = SessionManager.instance().get_session(session_id, db)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if session.session_type != "workspace":
        raise HTTPException(status_code=400, detail="Cannot rename telegram session")

    new_name = data.workspace_name.strip()
    if not new_name:
        raise HTTPException(status_code=422, detail="Workspace name required")

    row = (
        db.query(MaestroSession)
        .filter(MaestroSession.id == str(session_id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    row.workspace_name = new_name
    row.updated_at = datetime.now(timezone.utc)
    db.commit()

    session.workspace_name = new_name
    session.dirty = True

    return {
        "session_id": str(session.session_id),
        "workspace_name": new_name,
    }


@router.get("/sessions/{session_id}/history")
def session_history(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    session = SessionManager.instance().get_session(session_id, db)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    turns = _build_turn_history(session.maestro_messages or [])
    return {"session_id": str(session.session_id), "turns": turns}


@router.delete("/sessions/{session_id}")
def close_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    session = SessionManager.instance().get_session(session_id, db)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    SessionManager.instance().close_session(session_id, db)
    return {"status": "closed"}


@router.post("/sessions/{session_id}/reset")
def reset_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    session = SessionManager.instance().get_session(session_id, db)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    new_session = SessionManager.instance().reset_session(session_id, db)
    return {"session_id": str(new_session.session_id)}


@router.post("/sessions/{session_id}/compact")
def compact_session(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    session = SessionManager.instance().get_session(session_id, db)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    SessionManager.instance().compact_session(session, db)
    return {"status": "compacted"}


@router.post("/sessions/{session_id}/query")
async def query_session(
    session_id: UUID,
    data: QueryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    session = SessionManager.instance().get_session(session_id, db)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    async def event_generator():
        for queued in _drain_event_bus(session):
            yield f"data: {json.dumps(queued)}\n\n"
        async for event in run_maestro_turn(session, data.message, db):
            yield f"data: {json.dumps(event)}\n\n"
            for queued in _drain_event_bus(session):
                yield f"data: {json.dumps(queued)}\n\n"
        for queued in _drain_event_bus(session):
            yield f"data: {json.dumps(queued)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/projects/{project_id}/experience")
def list_experience(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    _verify_project(project_id, user, db)
    rows = (
        db.query(ExperienceFile)
        .filter(ExperienceFile.project_id == str(project_id))
        .order_by(ExperienceFile.path.asc())
        .all()
    )
    return [
        {
            "path": row.path,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]


@router.get("/projects/{project_id}/experience/{path:path}")
def read_experience(
    project_id: UUID,
    path: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _verify_project(project_id, user, db)
    row = (
        db.query(ExperienceFile)
        .filter(ExperienceFile.project_id == str(project_id))
        .filter(ExperienceFile.path == path)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Experience file not found")
    return {"path": row.path, "content": row.content}


# ─────────────────────────────────────────────────────────────────────
# Phase 7: Admin Benchmark Endpoints
# ─────────────────────────────────────────────────────────────────────


@router.get("/admin/benchmark")
def get_benchmark_report(
    project_id: UUID,
    days: int = 30,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Get benchmark evolution report for a project.

    Returns scoring dimension trends, correction rates, and insights over time.
    This is an admin endpoint for developers to evaluate Maestro quality.
    """
    _verify_project(project_id, user, db)
    return generate_evolution_report(project_id, days=days, db=db)


@router.get("/admin/benchmark/dimensions")
def get_benchmark_dimensions(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Get summary of all scoring dimensions for a project.

    Returns average, min, max, and count for each emergent dimension.
    """
    _verify_project(project_id, user, db)
    return {"dimensions": get_dimension_summary(project_id, db=db)}


@router.get("/admin/benchmark/corrections")
def get_benchmark_corrections(
    project_id: UUID,
    limit: int = 10,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Get recent interactions where the user corrected Maestro.

    Useful for reviewing what Maestro got wrong.
    """
    _verify_project(project_id, user, db)
    return {"corrections": get_recent_corrections(project_id, limit=limit, db=db)}
