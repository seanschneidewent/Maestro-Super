"""Discipline CRUD endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.database.session import get_db
from app.models.discipline import Discipline
from app.models.page import Page
from app.models.pointer import Pointer
from app.models.pointer_reference import PointerReference
from app.models.project import Project
from app.schemas.discipline import DisciplineCreate, DisciplineResponse, DisciplineUpdate
from app.services.gemini import analyze_discipline_pass3

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


@router.post("/disciplines/{discipline_id}/process-rollup")
async def process_discipline_rollup(
    discipline_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Process discipline rollup: Generate summary from all pages."""
    discipline = db.query(Discipline).filter(Discipline.id == discipline_id).first()
    if not discipline:
        raise HTTPException(status_code=404, detail="Discipline not found")

    # Get all pages in discipline with full_context
    pages = (
        db.query(Page)
        .filter(Page.discipline_id == discipline_id)
        .order_by(Page.page_name)
        .all()
    )

    page_summaries = [
        {"page_name": p.page_name, "full_context": p.full_context or p.initial_context or ""}
        for p in pages
    ]

    # Get outbound references from this discipline to other disciplines
    outbound_refs = (
        db.query(PointerReference)
        .join(Pointer, PointerReference.source_pointer_id == Pointer.id)
        .join(Page, Pointer.page_id == Page.id)
        .filter(Page.discipline_id == discipline_id)
        .options(
            joinedload(PointerReference.source_pointer).joinedload(Pointer.page),
            joinedload(PointerReference.target_page).joinedload(Page.discipline),
        )
        .all()
    )

    # Format references, excluding same-discipline refs
    cross_discipline_refs = []
    for ref in outbound_refs:
        target_disc = ref.target_page.discipline
        if target_disc.id != discipline_id:
            cross_discipline_refs.append({
                "source_page": ref.source_pointer.page.page_name,
                "target_page": ref.target_page.page_name,
                "target_discipline": target_disc.display_name,
            })

    logger.info(
        f"Processing rollup for {discipline.display_name} with "
        f"{len(pages)} pages, {len(cross_discipline_refs)} cross-refs"
    )

    # Call Gemini
    summary = await analyze_discipline_pass3(
        discipline_name=discipline.display_name,
        page_summaries=page_summaries,
        outbound_references=cross_discipline_refs,
    )

    # Update discipline
    discipline.summary = summary
    discipline.processed = True
    db.commit()

    logger.info(f"Rollup complete for discipline {discipline.display_name}")

    return {
        "discipline_id": discipline_id,
        "discipline_name": discipline.display_name,
        "summary": summary,
        "page_count": len(pages),
        "cross_reference_count": len(cross_discipline_refs),
    }
