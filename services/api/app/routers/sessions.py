"""Session CRUD endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import get_current_user
from app.auth.schemas import User
from app.database.session import get_db
from app.models.page import Page
from app.models.project import Project
from app.models.query import Query
from app.models.query_page import QueryPage
from app.models.session import Session as SessionModel
from app.schemas.session import SessionCreate, SessionResponse, SessionWithQueries

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sessions"])


def verify_project_exists(project_id: str, db: Session) -> Project:
    """Verify project exists."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post(
    "/projects/{project_id}/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionModel:
    """Create a new session for the current user."""
    verify_project_exists(project_id, db)

    session = SessionModel(
        user_id=user.id,
        project_id=project_id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    logger.info(f"Created session {session.id} for user {user.id} on project {project_id}")
    return session


@router.get(
    "/projects/{project_id}/sessions",
    response_model=list[SessionResponse],
)
def list_sessions(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    """List all sessions for a project with titles (filtered to current user, most recent first)."""
    verify_project_exists(project_id, db)

    # Subquery: get first query's display_title per session (by sequence_order, fallback to created_at)
    first_query_subq = (
        select(Query.display_title)
        .where(Query.session_id == SessionModel.id)
        .where(Query.hidden == False)
        .order_by(Query.sequence_order.asc().nulls_last(), Query.created_at.asc())
        .limit(1)
        .correlate(SessionModel)
        .scalar_subquery()
    )

    results = (
        db.query(
            SessionModel,
            first_query_subq.label("title")
        )
        .filter(SessionModel.project_id == project_id)
        .filter(SessionModel.user_id == user.id)
        .order_by(SessionModel.created_at.desc())
        .all()
    )

    return [
        {
            "id": session.id,
            "user_id": session.user_id,
            "project_id": session.project_id,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "title": title,
        }
        for session, title in results
    ]


@router.get(
    "/sessions/{session_id}",
    response_model=SessionWithQueries,
)
def get_session_with_queries(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionModel:
    """Get a session with all its queries and their pages (must be owned by current user)."""
    session = (
        db.query(SessionModel)
        .options(
            joinedload(SessionModel.queries)
            .joinedload(Query.query_pages)
            .joinedload(QueryPage.page)
        )
        .filter(SessionModel.id == session_id)
        .filter(SessionModel.user_id == user.id)
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a session and all its queries (cascade)."""
    session = (
        db.query(SessionModel)
        .filter(SessionModel.id == session_id)
        .filter(SessionModel.user_id == user.id)
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    db.delete(session)
    db.commit()

    logger.info(f"Deleted session {session_id} for user {user.id}")
