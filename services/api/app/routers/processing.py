"""Processing endpoints for page and discipline analysis."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import SessionLocal, get_db
from app.models.discipline import Discipline
from app.models.page import Page
from app.models.project import Project
from app.services.gemini import analyze_page_pass_1
from app.services.pdf_processor import extract_full_page_text, pdf_page_to_image
from app.services.storage import download_file, upload_page_image

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


class PageProcessResult(BaseModel):
    """Result for a single page in the upload processing pipeline."""

    page_id: str
    success: bool
    ocr_success: bool = False
    png_success: bool = False
    ai_success: bool = False
    error: str | None = None


class ProcessUploadsResult(BaseModel):
    """Response for the full upload processing pipeline."""

    total: int
    ocr_completed: int
    png_completed: int
    ai_completed: int
    failed: int
    results: list[PageProcessResult]


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

        # 4. Send to Gemini for analysis
        logger.info(f"Sending page {page_id} to Gemini for Pass 1 analysis")
        initial_context = await analyze_page_pass_1(image_bytes)

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

    Downloads the PDF, converts to image, sends to Gemini for analysis,
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


async def _process_page_ocr(page_id: str, db: Session) -> tuple[bool, str | None]:
    """
    Process OCR for a single page.

    Downloads PDF, extracts full text and word positions using PyMuPDF.
    Returns (success, error_message).
    """
    try:
        page = db.query(Page).filter(Page.id == page_id).first()
        if not page:
            return False, "Page not found"

        # Download PDF
        logger.info(f"OCR: Downloading PDF for page {page_id}")
        pdf_bytes = await download_file(page.file_path)

        # Extract text and word positions
        logger.info(f"OCR: Extracting text for page {page_id}")
        ocr_result = extract_full_page_text(pdf_bytes, page_index=0)

        # Update database
        page.full_page_text = ocr_result["text"]
        page.ocr_data = ocr_result["spans"]
        page.processed_ocr = True
        db.commit()

        logger.info(f"OCR complete for page {page_id}: {len(ocr_result['spans'])} spans")
        return True, None

    except Exception as e:
        logger.error(f"OCR failed for page {page_id}: {e}")
        db.rollback()
        return False, str(e)


async def _process_page_png(
    page_id: str, project_id: str, pdf_bytes: bytes, db: Session
) -> tuple[bool, str | None]:
    """
    Render and upload PNG for a single page.

    Returns (success, error_message).
    """
    try:
        page = db.query(Page).filter(Page.id == page_id).first()
        if not page:
            return False, "Page not found"

        # Convert to PNG at 150 DPI
        logger.info(f"PNG: Rendering page {page_id} at 150 DPI")
        image_bytes = pdf_page_to_image(pdf_bytes, page_index=0, dpi=150)

        # Upload to Supabase Storage
        logger.info(f"PNG: Uploading image for page {page_id}")
        storage_path = await upload_page_image(image_bytes, project_id, str(page_id))

        # Update database
        page.page_image_path = storage_path
        page.page_image_ready = True
        db.commit()

        logger.info(f"PNG complete for page {page_id}: {storage_path}")
        return True, None

    except Exception as e:
        logger.error(f"PNG failed for page {page_id}: {e}")
        db.rollback()
        return False, str(e)


async def _process_page_ai(
    page_id: str, pdf_bytes: bytes, db: Session
) -> tuple[bool, str | None]:
    """
    Run AI Pass 1 analysis for a single page.

    Sends the PDF image + OCR text to Gemini for initial context.
    Returns (success, error_message).
    """
    try:
        page = db.query(Page).filter(Page.id == page_id).first()
        if not page:
            return False, "Page not found"

        # Convert to image for Gemini
        logger.info(f"AI: Converting PDF to image for page {page_id}")
        image_bytes = pdf_page_to_image(pdf_bytes, page_index=0, dpi=150)

        # Send to Gemini (OCR text is now available for enhanced prompting)
        logger.info(f"AI: Sending page {page_id} to Gemini for Pass 1")
        initial_context = await analyze_page_pass_1(image_bytes)

        # Update database
        page.initial_context = initial_context
        page.processed_pass_1 = True
        db.commit()

        logger.info(f"AI Pass 1 complete for page {page_id}")
        return True, None

    except Exception as e:
        logger.error(f"AI failed for page {page_id}: {e}")
        db.rollback()
        return False, str(e)


@router.post(
    "/projects/{project_id}/process-uploads",
    response_model=ProcessUploadsResult,
)
async def process_uploads(
    project_id: str,
    db: Session = Depends(get_db),
) -> ProcessUploadsResult:
    """
    Process all unprocessed pages in a project after upload.

    Pipeline stages:
    1. OCR extraction (sequential, fast ~100ms each)
    2. AI + PNG processing (parallel, max 5 concurrent)

    This endpoint is called after files are uploaded to run the full
    processing pipeline with progress tracking.
    """
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get all unprocessed pages (need OCR or PNG or AI)
    pages = (
        db.query(Page)
        .join(Discipline)
        .filter(
            Discipline.project_id == project_id,
            # Any of these being incomplete means we need to process
            (Page.processed_ocr == False)  # noqa: E712
            | (Page.page_image_ready == False)  # noqa: E712
            | (Page.processed_pass_1 == False),  # noqa: E712
        )
        .all()
    )

    if not pages:
        return ProcessUploadsResult(
            total=0,
            ocr_completed=0,
            png_completed=0,
            ai_completed=0,
            failed=0,
            results=[],
        )

    logger.info(f"Starting upload processing for project {project_id}: {len(pages)} pages")

    results: list[PageProcessResult] = []
    ocr_completed = 0
    png_completed = 0
    ai_completed = 0
    failed = 0

    # Stage 1: OCR extraction (sequential - fast, shares PDF download)
    pdf_cache: dict[str, bytes] = {}  # Cache downloaded PDFs for reuse

    for page in pages:
        page_id = str(page.id)

        if not page.processed_ocr:
            # Download and cache PDF
            if page.file_path not in pdf_cache:
                try:
                    pdf_cache[page.file_path] = await download_file(page.file_path)
                except Exception as e:
                    logger.error(f"Failed to download PDF for page {page_id}: {e}")
                    results.append(
                        PageProcessResult(
                            page_id=page_id,
                            success=False,
                            error=f"PDF download failed: {e}",
                        )
                    )
                    failed += 1
                    continue

            with SessionLocal() as ocr_db:
                success, _ = await _process_page_ocr(page_id, ocr_db)
                if success:
                    ocr_completed += 1

    logger.info(f"OCR stage complete: {ocr_completed}/{len(pages)} succeeded")

    # Stage 2: AI + PNG in parallel (max 5 concurrent)
    semaphore = asyncio.Semaphore(5)

    async def process_ai_and_png(page: Page) -> PageProcessResult:
        page_id = str(page.id)
        result = PageProcessResult(page_id=page_id, success=True, ocr_success=True)

        async with semaphore:
            # Get cached PDF or download
            pdf_bytes = pdf_cache.get(page.file_path)
            if not pdf_bytes:
                try:
                    pdf_bytes = await download_file(page.file_path)
                    pdf_cache[page.file_path] = pdf_bytes
                except Exception as e:
                    result.success = False
                    result.error = f"PDF download failed: {e}"
                    return result

            # Run PNG and AI processing
            if not page.page_image_ready:
                with SessionLocal() as png_db:
                    png_success, png_error = await _process_page_png(
                        page_id, project_id, pdf_bytes, png_db
                    )
                    result.png_success = png_success
                    if not png_success:
                        result.error = png_error
            else:
                result.png_success = True

            if not page.processed_pass_1:
                with SessionLocal() as ai_db:
                    ai_success, ai_error = await _process_page_ai(
                        page_id, pdf_bytes, ai_db
                    )
                    result.ai_success = ai_success
                    if not ai_success and not result.error:
                        result.error = ai_error
            else:
                result.ai_success = True

            result.success = result.png_success and result.ai_success
            return result

    # Process all pages through AI + PNG stage
    stage2_results = await asyncio.gather(
        *[process_ai_and_png(page) for page in pages]
    )

    # Merge results
    for r in stage2_results:
        # Find if we already have a result for this page (from OCR failure)
        existing = next((x for x in results if x.page_id == r.page_id), None)
        if existing:
            continue  # Skip - already recorded as failed

        results.append(r)
        if r.png_success:
            png_completed += 1
        if r.ai_success:
            ai_completed += 1
        if not r.success:
            failed += 1

    logger.info(
        f"Upload processing complete for project {project_id}: "
        f"OCR={ocr_completed}, PNG={png_completed}, AI={ai_completed}, Failed={failed}"
    )

    return ProcessUploadsResult(
        total=len(pages),
        ocr_completed=ocr_completed,
        png_completed=png_completed,
        ai_completed=ai_completed,
        failed=failed,
        results=results,
    )
