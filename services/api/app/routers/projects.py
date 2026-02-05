"""Project CRUD endpoints."""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import get_current_user, get_current_user_or_anon
from app.auth.schemas import User
from app.config import get_settings
from app.database.session import get_db
from app.models.discipline import Discipline
from app.models.page import Page
from app.models.pointer import Pointer
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.schemas.search import SearchResponse, SearchResult
from app.services.voyage import embed_pointer as generate_embedding
from app.services.search import search_pointers

from app.schemas.upload import (
    BulkUploadRequest,
    BulkUploadResponse,
    DisciplineWithPagesResponse,
    PageInDisciplineResponse,
)
from app.schemas.hierarchy import ProjectHierarchyResponse
from app.services.v3.experience import seed_default_experience

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    """Create a new project for the current user."""
    project = Project(user_id=user.id, name=data.name)
    db.add(project)
    db.commit()
    db.refresh(project)

    # Seed default Experience files for V3
    try:
        seed_default_experience(project.id, db)
    except Exception as e:
        logger.warning("Failed to seed Experience for project %s: %s", project.id, e)

    return project


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Project]:
    """List all projects for the current user."""
    return db.query(Project).filter(Project.user_id == user.id).all()


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    """Get a specific project owned by the current user."""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == user.id,
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    data: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    """Update a project owned by the current user."""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == user.id,
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a project owned by the current user (cascades to all related data)."""
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == user.id,
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    db.delete(project)
    db.commit()


@router.post("/upload", response_model=BulkUploadResponse, status_code=status.HTTP_201_CREATED)
def bulk_upload(
    data: BulkUploadRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Create a project with disciplines and pages in a single transaction.
    Files must already be uploaded to Supabase Storage.
    """
    # Create project
    project = Project(user_id=user.id, name=data.project_name)
    db.add(project)
    db.flush()  # Get project ID without committing

    discipline_responses = []

    for disc_data in data.disciplines:
        # Skip empty disciplines
        if not disc_data.pages:
            continue

        # Create discipline
        discipline = Discipline(
            project_id=project.id,
            name=disc_data.code,
            display_name=disc_data.display_name,
        )
        db.add(discipline)
        db.flush()  # Get discipline ID

        page_responses = []
        for page_data in disc_data.pages:
            page = Page(
                discipline_id=discipline.id,
                page_name=page_data.page_name,
                file_path=page_data.storage_path,
            )
            db.add(page)
            db.flush()

            page_responses.append(
                PageInDisciplineResponse(
                    id=page.id,
                    page_name=page.page_name,
                    file_path=page.file_path,
                    processed_pass_1=page.processed_pass_1,
                    processed_pass_2=page.processed_pass_2,
                )
            )

        discipline_responses.append(
            DisciplineWithPagesResponse(
                id=discipline.id,
                project_id=discipline.project_id,
                name=discipline.name,
                display_name=discipline.display_name,
                processed=discipline.processed,
                pages=page_responses,
            )
        )

    db.commit()

    # Seed default Experience files for V3
    try:
        seed_default_experience(project.id, db)
    except Exception as e:
        logger.warning("Failed to seed Experience for project %s: %s", project.id, e)

    return {
        "project": project,
        "disciplines": discipline_responses,
    }


@router.get("/{project_id}/full", response_model=BulkUploadResponse)
def get_project_full(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Get a project with full hierarchy (disciplines and pages)."""
    project = (
        db.query(Project)
        .options(joinedload(Project.disciplines).joinedload(Discipline.pages))
        .filter(Project.id == project_id, Project.user_id == user.id)
        .first()
    )

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    discipline_responses = []
    for discipline in project.disciplines:
        page_responses = [
            PageInDisciplineResponse(
                id=page.id,
                page_name=page.page_name,
                file_path=page.file_path,
                processed_pass_1=page.processed_pass_1,
                processed_pass_2=page.processed_pass_2,
            )
            for page in sorted(discipline.pages, key=lambda p: p.page_name)
        ]

        discipline_responses.append(
            DisciplineWithPagesResponse(
                id=discipline.id,
                project_id=discipline.project_id,
                name=discipline.name,
                display_name=discipline.display_name,
                processed=discipline.processed,
                pages=page_responses,
            )
        )

    return {
        "project": project,
        "disciplines": discipline_responses,
    }


@router.get("/{project_id}/hierarchy", response_model=ProjectHierarchyResponse)
def get_project_hierarchy(
    project_id: str,
    user: User = Depends(get_current_user_or_anon),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Get project with full hierarchy including pointers and processing states.

    Returns a structure optimized for mind map visualization with:
    - Project name
    - Disciplines with processed status
    - Pages with pointer counts and processing states
    - Pointer titles for each page

    Anonymous users can only access the demo project.
    """
    settings = get_settings()

    # Anonymous users can only access the demo project
    if user.is_anonymous:
        if not settings.demo_project_id or str(project_id) != str(settings.demo_project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Anonymous users can only access the demo project"
            )
        # For demo project, don't filter by user_id
        project = (
            db.query(Project)
            .options(
                joinedload(Project.disciplines)
                .joinedload(Discipline.pages)
                .joinedload(Page.pointers)
            )
            .filter(Project.id == project_id)
            .first()
        )
    else:
        # Regular users: filter by ownership
        project = (
            db.query(Project)
            .options(
                joinedload(Project.disciplines)
                .joinedload(Discipline.pages)
                .joinedload(Page.pointers)
            )
            .filter(Project.id == project_id, Project.user_id == user.id)
            .first()
        )

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = {
        "id": str(project.id),
        "name": project.name,
        "disciplines": [
            {
                "id": str(d.id),
                "name": d.name,
                "displayName": d.display_name,
                "processed": d.processed,
                "pages": [
                    {
                        "id": str(p.id),
                        "pageName": p.page_name,
                        "pageIndex": p.page_index,
                        "processedPass1": p.processed_pass_1,
                        "processedPass2": p.processed_pass_2,
                        "pointerCount": len(p.pointers),
                        "pointers": [
                            {
                                "id": str(ptr.id),
                                "title": ptr.title,
                            }
                            for ptr in p.pointers
                        ],
                    }
                    for p in sorted(d.pages, key=lambda x: (
                        # Extract base name (strip page number prefix like "(1 of 8) ")
                        re.sub(r'^\(\d+ of \d+\)\s*', '', x.page_name),
                        # Then sort by page_index within same base name
                        x.page_index
                    ))
                ],
            }
            for d in sorted(project.disciplines, key=lambda x: x.display_name)
        ],
    }

    return JSONResponse(
        content=jsonable_encoder(result),
        headers={"Cache-Control": "no-store"},  # Disable caching to prevent stale page IDs
    )


@router.post("/{project_id}/backfill-embeddings")
async def backfill_embeddings(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Backfill embeddings for all pointers with null embedding.

    Processes all pointers in the project that don't have embeddings yet.
    Useful for existing pointers created before embedding was integrated.
    """
    # Verify project exists and user owns it
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == user.id,
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get all pointers in project without embeddings
    pointers = (
        db.query(Pointer)
        .join(Page)
        .join(Discipline)
        .filter(
            Discipline.project_id == project_id,
            Pointer.embedding == None,  # noqa: E711
        )
        .all()
    )

    success = 0
    failed = 0
    for pointer in pointers:
        try:
            embedding = await generate_embedding(
                pointer.title,
                pointer.description,
                pointer.text_spans,
            )
            pointer.embedding = embedding
            success += 1
        except Exception as e:
            logger.warning(f"Failed to embed pointer {pointer.id}: {e}")
            failed += 1

    db.commit()
    return {"backfilled": success, "failed": failed, "total": len(pointers)}


@router.get("/{project_id}/search", response_model=SearchResponse)
async def search_project(
    project_id: str,
    q: str,
    discipline: str | None = None,
    limit: int = 10,
    user: User = Depends(get_current_user_or_anon),
    db: Session = Depends(get_db),
) -> dict:
    """Search pointers in a project using hybrid keyword + vector search.

    Args:
        project_id: Project UUID
        q: Search query (min 2 characters)
        discipline: Optional discipline filter (e.g., "architectural")
        limit: Max results (default 10, max 50)

    Returns:
        Search results with relevance scores

    Anonymous users can only search the demo project.
    """
    settings = get_settings()

    # Anonymous users can only access the demo project
    if user.is_anonymous:
        if not settings.demo_project_id or str(project_id) != str(settings.demo_project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Anonymous users can only access the demo project"
            )
        # For demo project, don't filter by user_id
        project = db.query(Project).filter(Project.id == project_id).first()
    else:
        # Verify project exists and user owns it
        project = db.query(Project).filter(
            Project.id == project_id,
            Project.user_id == user.id,
        ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not q or len(q) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query must be at least 2 characters",
        )

    results = await search_pointers(
        db=db,
        query=q,
        project_id=project_id,
        discipline=discipline,
        limit=min(limit, 50),
    )

    return {
        "results": [SearchResult(**r) for r in results],
        "query": q,
        "count": len(results),
    }
