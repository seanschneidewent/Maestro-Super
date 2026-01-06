"""Pointer CRUD endpoints with AI analysis."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import get_current_user
from app.auth.schemas import User
from app.database.session import get_db
from app.dependencies.rate_limit import check_rate_limit
from app.models.page import Page
from app.models.pointer import Pointer
from app.models.pointer_reference import PointerReference
from app.schemas.pointer import (
    BoundingBoxCreate,
    PointerCreate,
    PointerResponse,
    PointerUpdate,
)
from app.services.usage import UsageService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pointers"])


def verify_page_exists(page_id: str, db: Session) -> Page:
    """Verify page exists and return it."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


@router.post(
    "/pages/{page_id}/pointers",
    response_model=PointerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_pointer(
    page_id: str,
    bbox: BoundingBoxCreate,
    user: User = Depends(check_rate_limit),
    db: Session = Depends(get_db),
) -> PointerResponse:
    """Create a pointer (bounding box only, no PDF processing).

    PDF processing has been removed. Pointers just store the bounding box coordinates.
    """
    # Get page and validate
    page = verify_page_exists(page_id, db)
    logger.info(f"Creating pointer on page {page.page_name} at ({bbox.x}, {bbox.y}) for user {user.id}")

    # Check pointer limit for project
    project_id = page.discipline.project_id
    allowed, error_info = UsageService.check_pointer_limit(db, user.id, project_id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_info,
        )

    try:
        # Create Pointer record (no PDF processing)
        pointer_id = str(uuid.uuid4())
        pointer = Pointer(
            id=pointer_id,
            page_id=page_id,
            title="New Pointer",
            description="",
            text_spans=[],
            ocr_data=[],
            bbox_x=bbox.x,
            bbox_y=bbox.y,
            bbox_width=bbox.width,
            bbox_height=bbox.height,
            png_path=None,
            needs_embedding=False,
        )
        db.add(pointer)
        db.commit()
        db.refresh(pointer)
        logger.info(f"Pointer {pointer_id} created successfully")

        # Track usage
        UsageService.increment_pointers(db, user.id)
        UsageService.increment_request(db, user.id)

        return PointerResponse.from_orm_with_embedding_check(pointer)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Pointer creation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create pointer. Please try again.",
        )


@router.post(
    "/pages/{page_id}/pointers/manual",
    response_model=PointerResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_pointer_manual(
    page_id: str,
    data: PointerCreate,
    db: Session = Depends(get_db),
) -> PointerResponse:
    """Create a pointer manually without AI analysis.

    Use this for testing or when you want to provide your own
    title, description, and text_spans.
    """
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
    """Get a specific pointer with references."""
    pointer = (
        db.query(Pointer)
        .options(
            joinedload(Pointer.outbound_references).joinedload(PointerReference.target_page)
        )
        .filter(Pointer.id == pointer_id)
        .first()
    )
    if not pointer:
        raise HTTPException(status_code=404, detail="Pointer not found")
    return PointerResponse.from_orm_with_embedding_check(pointer, include_references=True)


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
