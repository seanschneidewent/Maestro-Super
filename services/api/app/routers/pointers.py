"""ContextPointer CRUD endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import User
from app.database.session import get_db
from app.models.context_pointer import ContextPointer
from app.models.project import Project
from app.models.project_file import ProjectFile
from app.schemas.context_pointer import (
    ContextPointerCreate,
    ContextPointerResponse,
    ContextPointerUpdate,
)

router = APIRouter(tags=["pointers"])


def verify_file_access(file_id: str, user_id: str, db: Session) -> ProjectFile:
    """Verify user has access to file via project ownership."""
    file = (
        db.query(ProjectFile)
        .join(Project, ProjectFile.project_id == Project.id)
        .filter(ProjectFile.id == file_id, Project.user_id == user_id)
        .first()
    )
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    return file


def verify_pointer_access(
    pointer_id: str, user_id: str, db: Session
) -> ContextPointer:
    """Verify user has access to pointer via file → project ownership."""
    pointer = (
        db.query(ContextPointer)
        .join(ProjectFile, ContextPointer.file_id == ProjectFile.id)
        .join(Project, ProjectFile.project_id == Project.id)
        .filter(ContextPointer.id == pointer_id, Project.user_id == user_id)
        .first()
    )
    if not pointer:
        raise HTTPException(status_code=404, detail="Pointer not found")
    return pointer


@router.post(
    "/files/{file_id}/pointers",
    response_model=ContextPointerResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_pointer(
    file_id: str,
    data: ContextPointerCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ContextPointerResponse:
    """Create a context pointer on a file page."""
    verify_file_access(file_id, user.id, db)

    pointer = ContextPointer(
        file_id=file_id,
        page_number=data.page_number,
        x_norm=data.bounds.x_norm,
        y_norm=data.bounds.y_norm,
        w_norm=data.bounds.w_norm,
        h_norm=data.bounds.h_norm,
        title=data.title,
        description=data.description,
    )
    db.add(pointer)
    db.commit()
    db.refresh(pointer)
    return ContextPointerResponse.from_orm(pointer)


@router.get("/files/{file_id}/pointers", response_model=list[ContextPointerResponse])
def list_pointers(
    file_id: str,
    page: int | None = Query(default=None, description="Filter by page number"),
    committed_only: bool = Query(default=False, description="Only return committed"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ContextPointerResponse]:
    """List context pointers for a file."""
    verify_file_access(file_id, user.id, db)

    query = db.query(ContextPointer).filter(ContextPointer.file_id == file_id)

    if page is not None:
        query = query.filter(ContextPointer.page_number == page)

    if committed_only:
        query = query.filter(ContextPointer.committed_at.isnot(None))

    pointers = query.order_by(ContextPointer.page_number, ContextPointer.created_at).all()
    return [ContextPointerResponse.from_orm(p) for p in pointers]


@router.get("/pointers/{pointer_id}", response_model=ContextPointerResponse)
def get_pointer(
    pointer_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ContextPointerResponse:
    """Get a specific context pointer."""
    pointer = verify_pointer_access(pointer_id, user.id, db)
    return ContextPointerResponse.from_orm(pointer)


@router.patch("/pointers/{pointer_id}", response_model=ContextPointerResponse)
def update_pointer(
    pointer_id: str,
    data: ContextPointerUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ContextPointerResponse:
    """Update a context pointer."""
    pointer = verify_pointer_access(pointer_id, user.id, db)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(pointer, field, value)

    db.commit()
    db.refresh(pointer)
    return ContextPointerResponse.from_orm(pointer)


@router.post("/pointers/{pointer_id}/commit", response_model=ContextPointerResponse)
def commit_pointer(
    pointer_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ContextPointerResponse:
    """Commit (publish) a context pointer."""
    pointer = verify_pointer_access(pointer_id, user.id, db)

    if pointer.committed_at:
        raise HTTPException(status_code=400, detail="Pointer already committed")

    pointer.committed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pointer)
    return ContextPointerResponse.from_orm(pointer)


@router.delete("/pointers/{pointer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pointer(
    pointer_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Delete a context pointer."""
    pointer = verify_pointer_access(pointer_id, user.id, db)
    db.delete(pointer)
    db.commit()
