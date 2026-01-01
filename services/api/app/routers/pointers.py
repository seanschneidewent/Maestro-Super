"""Pointer CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.page import Page
from app.models.pointer import Pointer
from app.schemas.pointer import PointerCreate, PointerResponse, PointerUpdate

router = APIRouter(tags=["pointers"])


def verify_page_exists(page_id: str, db: Session) -> Page:
    """Verify page exists."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


@router.post(
    "/pages/{page_id}/pointers",
    response_model=PointerResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_pointer(
    page_id: str,
    data: PointerCreate,
    db: Session = Depends(get_db),
) -> PointerResponse:
    """Create a pointer on a page."""
    verify_page_exists(page_id, db)

    pointer = Pointer(
        page_id=page_id,
        title=data.title,
        description=data.description,
        text_spans=data.text_spans,
        bbox_x=data.bbox_x,
        bbox_y=data.bbox_y,
        bbox_width=data.bbox_width,
        bbox_height=data.bbox_height,
        png_path=data.png_path,
    )
    db.add(pointer)
    db.commit()
    db.refresh(pointer)
    return PointerResponse.from_orm_with_embedding_check(pointer)


@router.get(
    "/pages/{page_id}/pointers",
    response_model=list[PointerResponse],
)
def list_pointers(
    page_id: str,
    db: Session = Depends(get_db),
) -> list[PointerResponse]:
    """List all pointers on a page."""
    verify_page_exists(page_id, db)
    pointers = (
        db.query(Pointer)
        .filter(Pointer.page_id == page_id)
        .order_by(Pointer.created_at)
        .all()
    )
    return [PointerResponse.from_orm_with_embedding_check(p) for p in pointers]


@router.get("/pointers/{pointer_id}", response_model=PointerResponse)
def get_pointer(
    pointer_id: str,
    db: Session = Depends(get_db),
) -> PointerResponse:
    """Get a specific pointer."""
    pointer = db.query(Pointer).filter(Pointer.id == pointer_id).first()
    if not pointer:
        raise HTTPException(status_code=404, detail="Pointer not found")
    return PointerResponse.from_orm_with_embedding_check(pointer)


@router.patch("/pointers/{pointer_id}", response_model=PointerResponse)
def update_pointer(
    pointer_id: str,
    data: PointerUpdate,
    db: Session = Depends(get_db),
) -> PointerResponse:
    """Update a pointer."""
    pointer = db.query(Pointer).filter(Pointer.id == pointer_id).first()
    if not pointer:
        raise HTTPException(status_code=404, detail="Pointer not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(pointer, field, value)

    db.commit()
    db.refresh(pointer)
    return PointerResponse.from_orm_with_embedding_check(pointer)


@router.delete("/pointers/{pointer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pointer(
    pointer_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete a pointer and all related data (cascades)."""
    pointer = db.query(Pointer).filter(Pointer.id == pointer_id).first()
    if not pointer:
        raise HTTPException(status_code=404, detail="Pointer not found")

    db.delete(pointer)
    db.commit()
