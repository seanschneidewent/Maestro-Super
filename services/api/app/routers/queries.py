"""Query CRUD endpoints."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import User
from app.config import get_settings
from app.database.session import get_db
from app.dependencies.rate_limit import check_rate_limit, check_rate_limit_or_anon
from app.models.project import Project
from app.models.query import Query
from app.models.query_page import QueryPage
from app.models.conversation import Conversation
from app.schemas.query import AgentQueryRequest, QueryCreate, QueryResponse, QueryUpdate
from app.services.agent import run_agent_query
from app.services.conversation_memory import fetch_conversation_history
from app.services.usage import UsageService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["queries"])


def extract_pages_from_trace(trace: list[dict]) -> list[dict]:
    """
    Extract ordered page sequence from agent trace.

    Uses tool_call inputs (not tool_results) to preserve the agent's intended
    page ordering. The tool_result from select_pages doesn't preserve order
    because the SQL query uses .in_() which returns arbitrary order.

    Returns:
        List of dicts: [{"page_id": str, "pointers": [{"pointer_id": str}, ...]}]
    """
    # Track pages in order they appear, with their pointers
    pages_seen: dict[str, list[dict]] = {}  # page_id -> list of pointer dicts
    page_order: list[str] = []  # Maintains insertion order

    # Build a map of pointer_id -> page_id from tool_results (for select_pointers)
    pointer_to_page: dict[str, str] = {}
    for step in trace:
        if step.get("type") == "tool_result" and step.get("tool") == "select_pointers":
            result = step.get("result", {})
            if isinstance(result, dict):
                for pointer in result.get("pointers", []):
                    pointer_id = pointer.get("pointer_id")
                    page_id = pointer.get("page_id")
                    if pointer_id and page_id:
                        pointer_to_page[pointer_id] = page_id

    # Process tool_calls to get the agent's intended ordering
    for step in trace:
        if step.get("type") != "tool_call":
            continue

        tool = step.get("tool")
        tool_input = step.get("input", {})

        if not isinstance(tool_input, dict):
            continue

        if tool == "select_pages":
            # Use the agent's page_ids input order (not the scrambled result order)
            for page_id in tool_input.get("page_ids", []):
                if page_id and page_id not in pages_seen:
                    pages_seen[page_id] = []
                    page_order.append(page_id)

        elif tool == "select_pointers":
            # Process pointers in input order, look up their page_ids
            for pointer_id in tool_input.get("pointer_ids", []):
                page_id = pointer_to_page.get(pointer_id)
                if not page_id or not pointer_id:
                    continue

                if page_id not in pages_seen:
                    pages_seen[page_id] = []
                    page_order.append(page_id)

                # Add pointer to page's list (avoid duplicates)
                if not any(p.get("pointer_id") == pointer_id for p in pages_seen[page_id]):
                    pages_seen[page_id].append({"pointer_id": pointer_id})

    # Build final ordered list
    return [
        {"page_id": page_id, "pointers": pages_seen[page_id]}
        for page_id in page_order
    ]


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
    """List all queries for a project (filtered to current user, excludes hidden)."""
    verify_project_exists(project_id, db)

    return (
        db.query(Query)
        .filter(Query.project_id == project_id)
        .filter(Query.user_id == user.id)
        .filter(Query.hidden == False)
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


@router.patch("/queries/{query_id}/hide", status_code=status.HTTP_204_NO_CONTENT)
def hide_query(
    query_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Hide a query (soft delete - keeps in database but hidden from UI)."""
    query = db.query(Query).filter(Query.id == query_id).filter(Query.user_id == user.id).first()
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")

    query.hidden = True
    db.commit()


@router.post("/projects/{project_id}/queries/stream")
async def stream_query(
    project_id: str,
    data: AgentQueryRequest,
    user: User = Depends(check_rate_limit_or_anon),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """
    Stream agent query response via Server-Sent Events.

    Rate limited per user. Tracks token usage. Saves query to database.

    Yields SSE events:
    - data: {"type": "text", "content": "..."} - Claude's reasoning
    - data: {"type": "tool_call", "tool": "...", "input": {...}} - Tool being called
    - data: {"type": "tool_result", "tool": "...", "result": {...}} - Tool result
    - data: {"type": "done", "trace": [...], "usage": {...}, "displayTitle": "...", "conversationTitle": "..."} - Final event
    - data: {"type": "error", "message": "..."} - Error event
    """
    verify_project_exists(project_id, db)

    # Anonymous users can only query the demo project
    settings = get_settings()
    if user.is_anonymous and str(project_id) != str(settings.demo_project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Anonymous users can only access the demo project"
        )

    logger.info(f"Starting query stream for user {user.id} on project {project_id}")

    # Validate conversation if provided
    conversation_id = data.conversation_id
    sequence_order = None
    if conversation_id:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .filter(Conversation.user_id == user.id)
            .first()
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        # Compare as strings to handle UUID vs string mismatch
        if str(conversation.project_id) != str(project_id):
            raise HTTPException(status_code=400, detail="Conversation belongs to a different project")

        # Calculate sequence_order as count of existing queries in conversation + 1
        existing_count = (
            db.query(Query)
            .filter(Query.conversation_id == conversation_id)
            .count()
        )
        sequence_order = existing_count + 1
        logger.info(f"Query will be #{sequence_order} in conversation {conversation_id}")

    # Create query record in database
    query_record = Query(
        user_id=user.id,
        project_id=project_id,
        query_text=data.query,
        conversation_id=conversation_id,
        sequence_order=sequence_order,
    )
    db.add(query_record)
    db.commit()
    db.refresh(query_record)
    query_id = str(query_record.id)
    logger.info(f"Created query record {query_id}")

    # Increment request count
    UsageService.increment_request(db, user.id)

    # Fetch conversation history for multi-turn conversations
    history_messages: list[dict] = []
    if conversation_id:
        try:
            history_messages = fetch_conversation_history(
                db=db,
                conversation_id=conversation_id,
                exclude_query_id=query_id,
            )
        except Exception as e:
            logger.warning(f"Failed to load conversation history: {e}")
            # Continue without history - don't fail the query

    async def event_generator():
        total_tokens = 0
        response_text = ""
        display_title = None
        conversation_title_from_agent = None
        referenced_pointers = []
        stored_trace = []
        # Extract page context if provided
        page_context = data.page_context.model_dump() if data.page_context else None

        try:
            async for event in run_agent_query(
                db, project_id, data.query, history_messages=history_messages, response_mode=data.response_mode, page_context=page_context
            ):
                # Track tokens from done event and extract final answer
                if event.get("type") == "done":
                    usage = event.get("usage", {})
                    total_tokens = usage.get("inputTokens", 0) + usage.get("outputTokens", 0)
                    # Extract titles if provided by agent
                    display_title = event.get("displayTitle")
                    conversation_title_from_agent = event.get("conversationTitle")
                    # Extract the final response from trace
                    trace = event.get("trace", [])
                    stored_trace = trace  # Save for storage
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
            # Update query record with response, trace, and display_title
            try:
                query_record.response_text = response_text or None
                query_record.display_title = display_title
                query_record.tokens_used = total_tokens
                query_record.referenced_pointers = referenced_pointers if referenced_pointers else None
                query_record.trace = stored_trace if stored_trace else None
                db.commit()
                logger.info(f"Updated query {query_id} with response ({total_tokens} tokens), title: {display_title}")
            except Exception as e:
                logger.warning(f"Failed to update query record: {e}")

            # Create QueryPage records for the page sequence
            try:
                pages_data = extract_pages_from_trace(stored_trace)
                for order, page_data in enumerate(pages_data, start=1):
                    query_page = QueryPage(
                        query_id=query_id,
                        page_id=page_data["page_id"],
                        page_order=order,
                        pointers_shown=page_data["pointers"] if page_data["pointers"] else None,
                    )
                    db.add(query_page)
                if pages_data:
                    db.commit()
                    logger.info(f"Created {len(pages_data)} QueryPage records for query {query_id}")
            except Exception as e:
                logger.warning(f"Failed to create QueryPage records: {e}")

            # Track token usage
            if total_tokens > 0:
                try:
                    UsageService.increment_tokens(db, user.id, total_tokens)
                    logger.info(f"Tracked {total_tokens} tokens for user {user.id}")
                except Exception as e:
                    logger.warning(f"Failed to track tokens: {e}")

            # Update conversation title
            if conversation_id and conversation_title_from_agent:
                try:
                    from datetime import datetime
                    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
                    if conv:
                        conv.title = conversation_title_from_agent
                        conv.updated_at = datetime.utcnow()
                        db.commit()
                        logger.info(f"Updated conversation {conversation_id} title to: {conversation_title_from_agent}")
                except Exception as e:
                    logger.warning(f"Failed to update conversation title: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
