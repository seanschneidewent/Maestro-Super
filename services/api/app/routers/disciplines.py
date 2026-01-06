"""Discipline CRUD endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.discipline import Discipline
from app.models.project import Project
from app.schemas.discipline import DisciplineCreate, DisciplineResponse, DisciplineUpdate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["disciplines"])


def verify_project_exists(project_id: str, db: Session) -> Project:
    """Verify project exists."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post(
    "/projects/{project_id}/disciplines",
    response_model=DisciplineResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_discipline(
    project_id: str,
    data: DisciplineCreate,
    db: Session = Depends(get_db),
) -> Discipline:
    """Create a discipline in a project."""
    verify_project_exists(project_id, db)

    discipline = Discipline(
        project_id=project_id,
        name=data.name,
        display_name=data.display_name,
    )
    db.add(discipline)
    db.commit()
    db.refresh(discipline)
    return discipline


@router.get(
    "/projects/{project_id}/disciplines",
    response_model=list[DisciplineResponse],
)
def list_disciplines(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[Discipline]:
    """List all disciplines in a project."""
    verify_project_exists(project_id, db)
    return db.query(Discipline).filter(Discipline.project_id == project_id).all()


@router.get("/disciplines/{discipline_id}", response_model=DisciplineResponse)
def get_discipline(
    discipline_id: str,
    db: Session = Depends(get_db),
) -> Discipline:
    """Get a specific discipline."""
    discipline = db.query(Discipline).filter(Discipline.id == discipline_id).first()
    if not discipline:
        raise HTTPException(status_code=404, detail="Discipline not found")
    return discipline


@router.patch("/disciplines/{discipline_id}", response_model=DisciplineResponse)
def update_discipline(
    discipline_id: str,
    data: DisciplineUpdate,
    db: Session = Depends(get_db),
) -> Discipline:
    """Update a discipline."""
    discipline = db.query(Discipline).filter(Discipline.id == discipline_id).first()
    if not discipline:
        raise HTTPException(status_code=404, detail="Discipline not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(discipline, field, value)

    db.commit()
    db.refresh(discipline)
    return discipline


@router.delete("/disciplines/{discipline_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_discipline(
    discipline_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete a discipline and all related data (cascades)."""
    discipline = db.query(Discipline).filter(Discipline.id == discipline_id).first()
    if not discipline:
        raise HTTPException(status_code=404, detail="Discipline not found")

    db.delete(discipline)
    db.commit()


