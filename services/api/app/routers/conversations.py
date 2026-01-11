"""Conversation CRUD endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import get_current_user
from app.auth.schemas import User
from app.database.session import get_db
from app.models.conversation import Conversation
from app.models.page import Page
from app.models.project import Project
from app.models.query import Query
from app.models.query_page import QueryPage
from app.schemas.conversation import ConversationCreate, ConversationResponse, ConversationWithQueries

logger = logging.getLogger(__name__)

router = APIRouter(tags=["conversations"])


def verify_project_exists(project_id: str, db: Session) -> Project:
    """Verify project exists."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post(
    "/projects/{project_id}/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Conversation:
    """Create a new conversation for the current user."""
    verify_project_exists(project_id, db)

    conversation = Conversation(
        user_id=user.id,
        project_id=project_id,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    logger.info(f"Created conversation {conversation.id} for user {user.id} on project {project_id}")
    return conversation


@router.get(
    "/projects/{project_id}/conversations",
    response_model=list[ConversationResponse],
)
def list_conversations(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Conversation]:
    """List all conversations for a project (filtered to current user, only those with queries, most recent first)."""
    verify_project_exists(project_id, db)

    # Only return conversations that have at least one non-hidden query
    conversations = (
        db.query(Conversation)
        .filter(Conversation.project_id == project_id)
        .filter(Conversation.user_id == user.id)
        .filter(
            exists(
                select(Query.id)
                .where(Query.conversation_id == Conversation.id)
                .where(Query.hidden == False)
            )
        )
        .order_by(Conversation.updated_at.desc())
        .all()
    )

    return conversations


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationWithQueries,
)
def get_conversation_with_queries(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Conversation:
    """Get a conversation with all its queries and their pages (must be owned by current user)."""
    conversation = (
        db.query(Conversation)
        .options(
            joinedload(Conversation.queries)
            .joinedload(Query.query_pages)
            .joinedload(QueryPage.page)
        )
        .filter(Conversation.id == conversation_id)
        .filter(Conversation.user_id == user.id)
        .first()
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a conversation and all its queries (cascade)."""
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id)
        .filter(Conversation.user_id == user.id)
        .first()
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.delete(conversation)
    db.commit()

    logger.info(f"Deleted conversation {conversation_id} for user {user.id}")
