"""ProjectFile CRUD endpoints."""

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import User
from app.database.session import get_db
from app.models.project import Project
from app.models.project_file import ProjectFile
from app.schemas.project_file import (
    ProjectFileCreate,
    ProjectFileResponse,
    ProjectFileTreeResponse,
    ProjectFileUpdate,
)

router = APIRouter(tags=["files"])


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


@router.post(
    "/projects/{project_id}/files",
    response_model=ProjectFileResponse,
    status_code=status.HTTP_201_CREATED,
)  # No trailing slash - matches frontend
def create_file(
    project_id: str,
    data: ProjectFileCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectFile:
    """Create a file or folder in a project."""
    verify_project_access(project_id, user.id, db)

    # Verify parent exists in same project if specified
    if data.parent_id:
        parent = db.query(ProjectFile).filter(
            ProjectFile.id == data.parent_id,
            ProjectFile.project_id == project_id,
        ).first()
        if not parent:
            raise HTTPException(status_code=400, detail="Parent folder not found")
        if not parent.is_folder:
            raise HTTPException(status_code=400, detail="Parent must be a folder")

    file = ProjectFile(
        project_id=project_id,
        name=data.name,
        file_type=data.file_type,
        storage_path=data.storage_path,
        page_count=data.page_count,
        is_folder=data.is_folder,
        parent_id=data.parent_id,
    )
    db.add(file)
    db.commit()
    db.refresh(file)
    return file


@router.get("/projects/{project_id}/files", response_model=list[ProjectFileResponse])
def list_files(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ProjectFile]:
    """List all files in a project (flat list)."""
    verify_project_access(project_id, user.id, db)
    return db.query(ProjectFile).filter(ProjectFile.project_id == project_id).all()


@router.get(
    "/projects/{project_id}/files/tree",
    response_model=list[ProjectFileTreeResponse],
)
def list_files_tree(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ProjectFileTreeResponse]:
    """List all files in a project as a tree structure."""
    verify_project_access(project_id, user.id, db)

    # Query files ordered by: folders first (is_folder DESC), then name alphabetically
    files = (
        db.query(ProjectFile)
        .filter(ProjectFile.project_id == project_id)
        .order_by(ProjectFile.is_folder.desc(), ProjectFile.name)
        .all()
    )

    # Build tree structure (order is preserved from query)
    children_map: dict[str | None, list[ProjectFile]] = defaultdict(list)
    for file in files:
        children_map[file.parent_id].append(file)

    # Get root files (no parent)
    root_files = children_map.get(None, [])
    return [
        ProjectFileTreeResponse.from_orm_with_children(f, children_map)
        for f in root_files
    ]


@router.get("/files/{file_id}", response_model=ProjectFileResponse)
def get_file(
    file_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectFile:
    """Get a specific file."""
    return verify_file_access(file_id, user.id, db)


@router.patch("/files/{file_id}", response_model=ProjectFileResponse)
def update_file(
    file_id: str,
    data: ProjectFileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectFile:
    """Update a file."""
    file = verify_file_access(file_id, user.id, db)

    # Verify new parent if changing
    if data.parent_id is not None:
        if data.parent_id:  # Non-empty parent_id
            parent = db.query(ProjectFile).filter(
                ProjectFile.id == data.parent_id,
                ProjectFile.project_id == file.project_id,
            ).first()
            if not parent:
                raise HTTPException(status_code=400, detail="Parent folder not found")
            if not parent.is_folder:
                raise HTTPException(status_code=400, detail="Parent must be a folder")
            # Prevent circular reference
            if parent.id == file.id:
                raise HTTPException(status_code=400, detail="Cannot be own parent")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(file, field, value)

    db.commit()
    db.refresh(file)
    return file


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    file_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Delete a file (cascades to children and pointers)."""
    file = verify_file_access(file_id, user.id, db)
    db.delete(file)
    db.commit()
