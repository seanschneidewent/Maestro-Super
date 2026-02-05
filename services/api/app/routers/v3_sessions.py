"""V3 session endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
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


class CreateSessionRequest(BaseModel):
    project_id: UUID
    session_type: Literal["workspace", "telegram"]
    workspace_name: Optional[str] = None


class QueryRequest(BaseModel):
    message: str


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
        "workspace_name": data.workspace_name,
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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    _verify_project(project_id, user, db)
    sessions = (
        db.query(MaestroSession)
        .filter(MaestroSession.project_id == str(project_id))
        .filter(MaestroSession.status == "active")
        .order_by(MaestroSession.updated_at.desc())
        .all()
    )
    return [
        {
            "session_id": row.id,
            "session_type": row.session_type,
            "workspace_name": row.workspace_name,
            "last_active_at": row.last_active_at.isoformat() if row.last_active_at else None,
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
