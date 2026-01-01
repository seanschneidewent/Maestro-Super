"""Page CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.discipline import Discipline
from app.models.page import Page
from app.schemas.page import PageCreate, PageResponse, PageUpdate

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
