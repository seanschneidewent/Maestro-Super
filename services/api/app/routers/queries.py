"""Query CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import User
from app.database.session import get_db
from app.models.project import Project
from app.models.query import Query
from app.schemas.query import QueryCreate, QueryResponse, QueryUpdate

router = APIRouter(tags=["queries"])


def verify_project_access(project_id: str, user_id: str, db: Session) -> Project:
    """Verify user has access to project."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == user_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def verify_query_access(query_id: str, user_id: str, db: Session) -> Query:
    """Verify user has access to query."""
    query = (
        db.query(Query)
        .filter(Query.id == query_id, Query.user_id == user_id)
        .first()
    )
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")
    return query


@router.post(
    "/projects/{project_id}/queries",
    response_model=QueryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_query(
    project_id: str,
    data: QueryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Query:
    """Create a new query (stores query, AI response added later)."""
    verify_project_access(project_id, user.id, db)

    query = Query(
        user_id=user.id,
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
    user: User = Depends(get_current_user),
) -> list[Query]:
    """List all queries for a project."""
    verify_project_access(project_id, user.id, db)

    return (
        db.query(Query)
        .filter(Query.project_id == project_id, Query.user_id == user.id)
        .order_by(Query.created_at.desc())
        .all()
    )


@router.get("/queries/{query_id}", response_model=QueryResponse)
def get_query(
    query_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Query:
    """Get a specific query."""
    return verify_query_access(query_id, user.id, db)


@router.patch("/queries/{query_id}", response_model=QueryResponse)
def update_query(
    query_id: str,
    data: QueryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Query:
    """Update a query (typically to add AI response)."""
    query = verify_query_access(query_id, user.id, db)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(query, field, value)

    db.commit()
    db.refresh(query)
    return query
