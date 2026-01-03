"""Query CRUD endpoints."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import User
from app.database.session import get_db
from app.dependencies.rate_limit import check_rate_limit
from app.models.project import Project
from app.models.query import Query
from app.schemas.query import AgentQueryRequest, QueryCreate, QueryResponse, QueryUpdate
from app.services.agent import run_agent_query
from app.services.usage import UsageService

logger = logging.getLogger(__name__)

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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Query]:
    """List all queries for a project (filtered to current user)."""
    verify_project_exists(project_id, db)

    return (
        db.query(Query)
        .filter(Query.project_id == project_id)
        .filter(Query.user_id == user.id)
        .order_by(Query.created_at.desc())
        .all()
    )


@router.get("/queries/{query_id}", response_model=QueryResponse)
def get_query(
    query_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Query:
    """Get a specific query (must be owned by current user)."""
    query = db.query(Query).filter(Query.id == query_id).filter(Query.user_id == user.id).first()
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
    user: User = Depends(check_rate_limit),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """
    Stream agent query response via Server-Sent Events.

    Rate limited per user. Tracks token usage. Saves query to database.

    Yields SSE events:
    - data: {"type": "text", "content": "..."} - Claude's reasoning
    - data: {"type": "tool_call", "tool": "...", "input": {...}} - Tool being called
    - data: {"type": "tool_result", "tool": "...", "result": {...}} - Tool result
    - data: {"type": "done", "trace": [...], "usage": {...}} - Final event
    - data: {"type": "error", "message": "..."} - Error event
    """
    verify_project_exists(project_id, db)
    logger.info(f"Starting query stream for user {user.id} on project {project_id}")

    # Create query record in database
    query_record = Query(
        user_id=user.id,
        project_id=project_id,
        query_text=data.query,
    )
    db.add(query_record)
    db.commit()
    db.refresh(query_record)
    query_id = str(query_record.id)
    logger.info(f"Created query record {query_id}")

    # Increment request count
    UsageService.increment_request(db, user.id)

    async def event_generator():
        total_tokens = 0
        response_text = ""
        referenced_pointers = []
        try:
            async for event in run_agent_query(db, project_id, data.query):
                # Track tokens from done event and extract final answer
                if event.get("type") == "done":
                    usage = event.get("usage", {})
                    total_tokens = usage.get("inputTokens", 0) + usage.get("outputTokens", 0)
                    # Extract the final response from trace
                    trace = event.get("trace", [])
                    # Find last reasoning steps after tool calls
                    last_tool_idx = -1
                    for i, step in enumerate(trace):
                        if step.get("type") == "tool_result":
                            last_tool_idx = i
                            # Collect pointer IDs from tool results
                            result = step.get("result", {})
                            if isinstance(result, dict):
                                if result.get("pointer_id"):
                                    referenced_pointers.append({"pointer_id": result["pointer_id"]})
                                elif result.get("pointers"):
                                    for p in result["pointers"]:
                                        if isinstance(p, dict) and p.get("id"):
                                            referenced_pointers.append({"pointer_id": p["id"]})
                    # Collect final answer text
                    for step in trace[last_tool_idx + 1:]:
                        if step.get("type") == "reasoning" and step.get("content"):
                            response_text += step["content"]

                yield f"data: {json.dumps(event)}\n\n"
        finally:
            # Update query record with response
            try:
                query_record.response_text = response_text or None
                query_record.tokens_used = total_tokens
                query_record.referenced_pointers = referenced_pointers if referenced_pointers else None
                db.commit()
                logger.info(f"Updated query {query_id} with response ({total_tokens} tokens)")
            except Exception as e:
                logger.warning(f"Failed to update query record: {e}")

            # Track token usage
            if total_tokens > 0:
                try:
                    UsageService.increment_tokens(db, user.id, total_tokens)
                    logger.info(f"Tracked {total_tokens} tokens for user {user.id}")
                except Exception as e:
                    logger.warning(f"Failed to track tokens: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
