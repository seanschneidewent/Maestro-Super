"""Processing endpoints for page and discipline analysis."""

import asyncio
import base64
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import SessionLocal, get_db
from app.models.discipline import Discipline
from app.models.page import Page
from app.services.claude import analyze_page_pass_1
from app.services.pdf_processor import pdf_page_to_image
from app.services.storage import download_file

logger = logging.getLogger(__name__)

router = APIRouter(tags=["processing"])


# Response schemas
class Pass1Result(BaseModel):
    """Response for single page Pass 1 processing."""

    success: bool
    page_id: str
    initial_context: str | None = None
    error: str | None = None


class BatchPass1Result(BaseModel):
    """Response for batch Pass 1 processing."""

    total: int
    processed: int
    failed: int
    results: list[Pass1Result]


async def _process_page_pass_1(page_id: str, db: Session) -> Pass1Result:
    """
    Internal function to process a single page through Pass 1.

    Args:
        page_id: Page UUID
        db: Database session

    Returns:
        Pass1Result with success status and context or error
    """
    try:
        # 1. Get page from database
        page = db.query(Page).filter(Page.id == page_id).first()
        if not page:
            return Pass1Result(
                success=False,
                page_id=page_id,
                error="Page not found",
            )

        # 2. Download PDF from Supabase Storage
        logger.info(f"Downloading PDF for page {page_id}: {page.file_path}")
        pdf_bytes = await download_file(page.file_path)

        # 3. Convert PDF page to PNG image
        logger.info(f"Converting PDF to image for page {page_id}")
        image_bytes = pdf_page_to_image(pdf_bytes, page_index=0, dpi=150)
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # 4. Send to Claude for analysis
        logger.info(f"Sending page {page_id} to Claude for Pass 1 analysis")
        initial_context = await analyze_page_pass_1(image_base64)

        # 5. Update database
        page.initial_context = initial_context
        page.processed_pass_1 = True
        db.commit()

        logger.info(f"Pass 1 complete for page {page_id}")
        return Pass1Result(
            success=True,
            page_id=page_id,
            initial_context=initial_context,
        )

    except Exception as e:
        logger.error(f"Pass 1 failed for page {page_id}: {e}")
        db.rollback()
        return Pass1Result(
            success=False,
            page_id=page_id,
            error=str(e),
        )


@router.post("/pages/{page_id}/process-pass-1", response_model=Pass1Result)
async def process_page_pass_1(
    page_id: str,
    db: Session = Depends(get_db),
) -> Pass1Result:
    """
    Process a single page through Pass 1.

    Downloads the PDF, converts to image, sends to Claude for analysis,
    and stores the initial context summary.
    """
    return await _process_page_pass_1(page_id, db)


@router.post(
    "/disciplines/{discipline_id}/process-all-pages-pass-1",
    response_model=BatchPass1Result,
)
async def process_all_pages_pass_1(
    discipline_id: str,
    db: Session = Depends(get_db),
) -> BatchPass1Result:
    """
    Process all unprocessed pages in a discipline through Pass 1.

    Runs up to 5 pages concurrently for faster processing.
    Each page gets its own database session to avoid SQLAlchemy session conflicts.
    """
    # Verify discipline exists
    discipline = db.query(Discipline).filter(Discipline.id == discipline_id).first()
    if not discipline:
        raise HTTPException(status_code=404, detail="Discipline not found")

    # Get all unprocessed page IDs (just IDs to avoid session binding issues)
    page_ids = [
        p.id
        for p in db.query(Page.id)
        .filter(
            Page.discipline_id == discipline_id,
            Page.processed_pass_1 == False,  # noqa: E712
        )
        .all()
    ]

    if not page_ids:
        return BatchPass1Result(
            total=0,
            processed=0,
            failed=0,
            results=[],
        )

    logger.info(
        f"Starting batch Pass 1 for discipline {discipline_id}: {len(page_ids)} pages"
    )

    # Semaphore limits concurrency to 5
    semaphore = asyncio.Semaphore(5)

    async def process_with_limit(page_id: str) -> Pass1Result:
        async with semaphore:
            # Each task gets its own session (SQLAlchemy sessions aren't thread-safe)
            with SessionLocal() as task_db:
                return await _process_page_pass_1(page_id, task_db)

    # Process all pages in parallel (max 5 at a time)
    results = await asyncio.gather(*[process_with_limit(pid) for pid in page_ids])

    processed = len([r for r in results if r.success])
    failed = len([r for r in results if not r.success])

    logger.info(
        f"Batch Pass 1 complete for discipline {discipline_id}: "
        f"{processed}/{len(page_ids)} succeeded, {failed} failed"
    )

    return BatchPass1Result(
        total=len(page_ids),
        processed=processed,
        failed=failed,
        results=list(results),
    )
