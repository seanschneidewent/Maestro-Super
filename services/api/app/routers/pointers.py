"""Pointer CRUD endpoints with AI analysis."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.discipline import Discipline
from app.models.page import Page
from app.models.pointer import Pointer
from app.models.pointer_reference import PointerReference
from app.schemas.pointer import (
    BoundingBoxCreate,
    PointerCreate,
    PointerResponse,
    PointerUpdate,
)
from app.services.gemini import analyze_pointer
from app.services.ocr import crop_pdf_region, extract_text_with_positions
from app.services.storage import download_file, upload_snapshot

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
    db: Session = Depends(get_db),
) -> PointerResponse:
    """Create a pointer with full AI analysis.

    Pipeline:
    1. Crop PDF to bounding box region
    2. Run Tesseract OCR to extract text with positions
    3. Get page context and all project page names
    4. Analyze with Gemini to generate title, description, references
    5. Upload cropped PNG to Supabase
    6. Create pointer and reference records
    """
    # 1. Get page and validate
    page = verify_page_exists(page_id, db)
    logger.info(f"Creating pointer on page {page.page_name} at ({bbox.x}, {bbox.y})")

    # 2. Download PDF from Supabase Storage
    logger.info(f"Downloading PDF: {page.file_path}")
    pdf_bytes = await download_file(page.file_path)

    # 3. Crop to bounding box region
    logger.info(f"Cropping region: ({bbox.x}, {bbox.y}, {bbox.width}, {bbox.height})")
    cropped_png = crop_pdf_region(
        pdf_bytes,
        page_index=0,  # Pages are single-page PDFs
        x_norm=bbox.x,
        y_norm=bbox.y,
        w_norm=bbox.width,
        h_norm=bbox.height,
    )

    # 4. Run Tesseract OCR
    logger.info("Running Tesseract OCR")
    ocr_spans = extract_text_with_positions(cropped_png)
    logger.info(f"OCR found {len(ocr_spans)} text spans")

    # 5. Get page context and all page names in project
    page_context = page.initial_context or ""

    # Get all page names in the same project
    all_pages = (
        db.query(Page.page_name)
        .filter(
            Page.discipline_id.in_(
                db.query(Discipline.id).filter(
                    Discipline.project_id == page.discipline.project_id
                )
            )
        )
        .all()
    )
    all_page_names = [p.page_name for p in all_pages]
    logger.info(f"Project has {len(all_page_names)} pages for reference matching")

    # 6. Analyze with Gemini
    logger.info("Sending to Gemini for analysis")
    analysis = await analyze_pointer(
        cropped_png,
        ocr_spans,
        page_context,
        all_page_names,
    )
    logger.info(f"Gemini analysis complete: {analysis.get('title', 'Unknown')}")

    # 7. Upload cropped PNG to Supabase
    pointer_id = str(uuid.uuid4())
    png_path = await upload_snapshot(
        cropped_png,
        pointer_id,
        "system",  # TODO: Get from auth when implemented
    )
    logger.info(f"Uploaded snapshot to {png_path}")

    # 8. Create Pointer record
    pointer = Pointer(
        id=pointer_id,
        page_id=page_id,
        title=analysis["title"],
        description=analysis["description"],
        text_spans=analysis.get("text_spans", []),
        ocr_data=ocr_spans,  # Full OCR data with word positions
        bbox_x=bbox.x,
        bbox_y=bbox.y,
        bbox_width=bbox.width,
        bbox_height=bbox.height,
        png_path=png_path,
    )
    db.add(pointer)

    # 9. Create PointerReference records for detected cross-references
    for ref in analysis.get("references", []):
        target_page_name = ref.get("target_page")
        if not target_page_name:
            continue

        # Find target page by name
        target_page = db.query(Page).filter(Page.page_name == target_page_name).first()

        if target_page:
            pointer_ref = PointerReference(
                id=str(uuid.uuid4()),
                source_pointer_id=pointer_id,
                target_page_id=target_page.id,
                justification=ref.get("justification", ""),
            )
            db.add(pointer_ref)
            logger.info(f"Created reference to page {target_page_name}")

    db.commit()
    db.refresh(pointer)
    logger.info(f"Pointer {pointer_id} created successfully")

    return PointerResponse.from_orm_with_embedding_check(pointer)


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
