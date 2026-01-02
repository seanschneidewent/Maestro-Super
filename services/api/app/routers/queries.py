"""Query CRUD endpoints."""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.project import Project
from app.models.query import Query
from app.schemas.query import AgentQueryRequest, QueryCreate, QueryResponse, QueryUpdate
from app.services.agent import run_agent_query

router = APIRouter(tags=["queries"])


def verify_project_exists(project_id: str, db: Session) -> Project:
    """Verify project exists."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post(
    "/projects/{project_id}/queries",
    response_model=QueryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_query(
    project_id: str,
    data: QueryCreate,
    user_id: str = "anonymous",  # Will be replaced with auth later
    db: Session = Depends(get_db),
) -> Query:
    """Create a new query (stores query, AI response added later)."""
    verify_project_exists(project_id, db)

    query = Query(
        user_id=user_id,
        project_id=project_id,
        query_text=data.query_text,
    )
    db.add(query)
    db.commit()
    db.refresh(query)
    return query


@router.get("/projects/{project_id}/queries", response_model=list[QueryResponse])
def list_queries(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[Query]:
    """List all queries for a project."""
    verify_project_exists(project_id, db)

    return (
        db.query(Query)
        .filter(Query.project_id == project_id)
        .order_by(Query.created_at.desc())
        .all()
    )


@router.get("/queries/{query_id}", response_model=QueryResponse)
def get_query(
    query_id: str,
    db: Session = Depends(get_db),
) -> Query:
    """Get a specific query."""
    query = db.query(Query).filter(Query.id == query_id).first()
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")
    return query


@router.patch("/queries/{query_id}", response_model=QueryResponse)
def update_query(
    query_id: str,
    data: QueryUpdate,
    db: Session = Depends(get_db),
) -> Query:
    """Update a query (typically to add AI response)."""
    query = db.query(Query).filter(Query.id == query_id).first()
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(query, field, value)

    db.commit()
    db.refresh(query)
    return query


@router.post("/projects/{project_id}/queries/stream")
async def stream_query(
    project_id: str,
    data: AgentQueryRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """
    Stream agent query response via Server-Sent Events.

    Yields SSE events:
    - data: {"type": "text", "content": "..."} - Claude's reasoning
    - data: {"type": "tool_call", "tool": "...", "input": {...}} - Tool being called
    - data: {"type": "tool_result", "tool": "...", "result": {...}} - Tool result
    - data: {"type": "done", "trace": [...], "usage": {...}} - Final event
    - data: {"type": "error", "message": "..."} - Error event
    """
    verify_project_exists(project_id, db)

    async def event_generator():
        async for event in run_agent_query(db, project_id, data.query):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
