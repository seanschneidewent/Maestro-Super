"""Page CRUD endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.database.session import get_db
from app.models.discipline import Discipline
from app.models.page import Page
from app.models.pointer import Pointer
from app.models.pointer_reference import PointerReference
from app.schemas.page import PageCreate, PageResponse, PageUpdate
from app.services.gemini import analyze_page_pass2

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pages"])


def verify_discipline_exists(discipline_id: str, db: Session) -> Discipline:
    """Verify discipline exists."""
    discipline = db.query(Discipline).filter(Discipline.id == discipline_id).first()
    if not discipline:
        raise HTTPException(status_code=404, detail="Discipline not found")
    return discipline


@router.post(
    "/disciplines/{discipline_id}/pages",
    response_model=PageResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_page(
    discipline_id: str,
    data: PageCreate,
    db: Session = Depends(get_db),
) -> Page:
    """Create a page in a discipline."""
    verify_discipline_exists(discipline_id, db)

    page = Page(
        discipline_id=discipline_id,
        page_name=data.page_name,
        file_path=data.file_path,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


@router.get(
    "/disciplines/{discipline_id}/pages",
    response_model=list[PageResponse],
)
def list_pages(
    discipline_id: str,
    db: Session = Depends(get_db),
) -> list[Page]:
    """List all pages in a discipline."""
    verify_discipline_exists(discipline_id, db)
    return (
        db.query(Page)
        .filter(Page.discipline_id == discipline_id)
        .order_by(Page.page_name)
        .all()
    )


@router.get("/pages/{page_id}", response_model=PageResponse)
def get_page(
    page_id: str,
    db: Session = Depends(get_db),
) -> Page:
    """Get a specific page."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


@router.patch("/pages/{page_id}", response_model=PageResponse)
def update_page(
    page_id: str,
    data: PageUpdate,
    db: Session = Depends(get_db),
) -> Page:
    """Update a page."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(page, field, value)

    db.commit()
    db.refresh(page)
    return page


@router.delete("/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_page(
    page_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete a page and all related data (cascades)."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    db.delete(page)
    db.commit()


@router.post("/pages/{page_id}/process-pass-2")
async def process_page_pass_2(
    page_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Process page Pass 2: Generate full_context from all pointers."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    # Get all pointers with their references
    pointers = (
        db.query(Pointer)
        .options(joinedload(Pointer.outbound_references).joinedload(PointerReference.target_page))
        .filter(Pointer.page_id == page_id)
        .all()
    )

    # Format pointer data for Gemini
    pointer_data = []
    for p in pointers:
        refs = [
            {"target_page": ref.target_page.page_name, "justification": ref.justification}
            for ref in p.outbound_references
        ]
        pointer_data.append({
            "title": p.title,
            "description": p.description,
            "text_spans": p.text_spans or [],
            "references": refs,
        })

    logger.info(f"Processing Pass 2 for page {page.page_name} with {len(pointer_data)} pointers")

    # Call Gemini
    full_context = await analyze_page_pass2(
        page_context=page.initial_context or "",
        pointers=pointer_data,
    )

    # Update page
    page.full_context = full_context
    page.processed_pass_2 = True
    db.commit()

    logger.info(f"Pass 2 complete for page {page.page_name}")

    return {
        "page_id": page_id,
        "page_name": page.page_name,
        "full_context": full_context,
        "pointer_count": len(pointer_data),
    }
