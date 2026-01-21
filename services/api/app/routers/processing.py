"""Processing endpoints for page analysis."""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import SessionLocal, get_db
from app.models.discipline import Discipline
from app.models.page import Page
from app.models.project import Project
from app.services.pdf_renderer import get_pdf_page_count, pdf_page_to_image
from app.services.storage import download_file, upload_page_image

logger = logging.getLogger(__name__)

router = APIRouter(tags=["processing"])


# ============================================================
# Pydantic models for bulk insert
# ============================================================


class PageInput(BaseModel):
    """Input for a single page in the upload plan."""

    page_name: str
    storage_path: str


class DisciplineInput(BaseModel):
    """Input for a discipline with its pages."""

    code: str
    display_name: str
    pages: list[PageInput]


class ProcessUploadsRequest(BaseModel):
    """Request body for process-uploads-stream endpoint."""

    disciplines: list[DisciplineInput]


async def _render_page_png(
    page_id: str,
    project_id: str,
    pdf_bytes: bytes,
    page_index: int = 0,
) -> tuple[str, bytes | None, str | None, str | None]:
    """
    Render PDF page to PNG and upload to storage.

    Args:
        page_id: Page ID string
        project_id: Project ID for storage path
        pdf_bytes: PDF bytes for this page
        page_index: Zero-based index within the PDF (default: 0)

    Returns:
        (page_id, png_bytes, storage_path, error_message)
        png_bytes/storage_path is None if rendering failed
    """
    try:
        # Render to PNG at 150 DPI with 30s timeout
        png_bytes = await asyncio.wait_for(
            asyncio.to_thread(pdf_page_to_image, pdf_bytes, page_index, 150),
            timeout=30.0,
        )

        # Upload to storage
        storage_path = await upload_page_image(png_bytes, project_id, page_id)

        logger.info(f"PNG complete for page {page_id}")
        return page_id, png_bytes, storage_path, None

    except Exception as e:
        logger.error(f"PNG failed for page {page_id}: {e}")
        return page_id, None, None, str(e)


@router.post("/projects/{project_id}/process-uploads-stream")
async def process_uploads_stream(
    project_id: str,
    request: ProcessUploadsRequest | None = None,
    # NOTE: Intentionally NOT using Depends(get_db) - SSE runs too long
):
    """
    SSE endpoint that streams progress updates as processing happens.

    Accepts optional request body with disciplines/pages to bulk-insert before processing.
    If no body provided, processes existing unprocessed pages.

    Pipeline:
    1. Bulk insert disciplines/pages (if request body provided)
    2. PNG stage (parallel): Render all pages to PNG, upload to storage
    3. Complete - app is immediately usable

    SSE events:
    - {"stage": "init", "pageCount": N}  (after bulk insert)
    - {"stage": "png", "current": N, "total": T}
    - {"stage": "png_failures", "pageIds": [...]}  (list of failed page IDs)
    - {"stage": "complete"}
    - {"stage": "error", "message": "..."}

    Heartbeat comment sent every 3 seconds to prevent connection timeout.
    """
    # Use manual session management - quick open/close, don't hold for SSE duration
    # Extract page data to dicts so we can close session before SSE starts
    page_data_list: list[dict] = []

    # First: verify project exists
    with SessionLocal() as db:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

    # Second: count pages in each PDF (async, before DB insert)
    pdf_page_counts: dict[str, int] = {}
    if request and request.disciplines:
        # Collect unique PDF paths
        unique_pdf_paths: set[str] = set()
        for disc_data in request.disciplines:
            for page_input in disc_data.pages:
                unique_pdf_paths.add(page_input.storage_path)

        # Download each unique PDF and count its pages
        for pdf_path in unique_pdf_paths:
            try:
                pdf_bytes = await download_file(pdf_path)
                page_count = get_pdf_page_count(pdf_bytes)
                pdf_page_counts[pdf_path] = page_count
                logger.info(f"PDF {pdf_path} has {page_count} page(s)")
            except Exception as e:
                logger.warning(f"Failed to count pages in {pdf_path}: {e}, defaulting to 1")
                pdf_page_counts[pdf_path] = 1

    # Third: bulk insert disciplines/pages
    with SessionLocal() as db:
        if request and request.disciplines:
            # Create disciplines and pages (splitting multi-page PDFs)
            for disc_data in request.disciplines:
                discipline = Discipline(
                    project_id=project_id,
                    name=disc_data.code,
                    display_name=disc_data.display_name,
                )
                db.add(discipline)
                db.flush()  # Get ID without committing

                for page_input in disc_data.pages:
                    page_count = pdf_page_counts.get(page_input.storage_path, 1)
                    base_name = page_input.page_name

                    # Create one Page record per page in the PDF
                    for idx in range(page_count):
                        # Format: "(X of Y) Name" for multi-page, original name for single-page
                        if page_count > 1:
                            page_name = f"({idx + 1} of {page_count}) {base_name}"
                        else:
                            page_name = base_name

                        page = Page(
                            discipline_id=str(discipline.id),
                            page_name=page_name,
                            file_path=page_input.storage_path,
                            page_index=idx,
                        )
                        db.add(page)

            db.commit()
            logger.info(f"Bulk inserted {len(request.disciplines)} disciplines for project {project_id}")

        # Get all pages needing PNG rendering (detach from ORM)
        pages = (
            db.query(Page)
            .join(Discipline)
            .filter(
                Discipline.project_id == project_id,
                Page.page_image_ready == False,  # noqa: E712
            )
            .all()
        )

        # Extract to simple dicts before session closes
        page_data_list = [
            {"id": str(p.id), "file_path": p.file_path, "page_index": p.page_index}
            for p in pages
        ]

    # Session is now closed - SSE can run without holding DB connection
    total = len(page_data_list)

    async def event_generator() -> AsyncGenerator[str, None]:
        # Emit init event with page count
        yield f"data: {json.dumps({'stage': 'init', 'pageCount': total})}\n\n"

        if total == 0:
            yield f"data: {json.dumps({'stage': 'complete'})}\n\n"
            return

        # ============================================================
        # On-demand PDF download with lock (prevents race condition + memory bloat)
        # ============================================================
        pdf_cache: dict[str, bytes] = {}
        pdf_cache_lock = asyncio.Lock()

        async def get_pdf_bytes(file_path: str) -> bytes:
            """Download PDF with lock to prevent race condition."""
            async with pdf_cache_lock:
                if file_path not in pdf_cache:
                    logger.info(f"Downloading PDF: {file_path}")
                    pdf_cache[file_path] = await download_file(file_path)
                return pdf_cache[file_path]

        # Semaphore for PNG concurrency (max 10)
        semaphore = asyncio.Semaphore(10)

        # ============================================================
        # Stage 1: PNG rendering (parallel) with GLOBAL TIMEOUT
        # ============================================================
        PNG_STAGE_TIMEOUT = 300  # 5 minutes max for entire PNG stage

        try:
            async def render_with_semaphore(page_data: dict) -> tuple[str, bytes | None, str | None, str | None]:
                try:
                    pdf_bytes = await get_pdf_bytes(page_data["file_path"])
                except Exception as e:
                    return page_data["id"], None, None, f"PDF download failed: {e}"
                async with semaphore:
                    return await _render_page_png(
                        page_data["id"],
                        project_id,
                        pdf_bytes,
                        page_data.get("page_index", 0),
                    )

            # Use asyncio.gather with return_exceptions=True to prevent stream crash
            # Run tasks and emit progress periodically
            tasks = [render_with_semaphore(p) for p in page_data_list]

            # Track progress with a wrapper that updates on completion
            completed = 0
            results: list[tuple[str, bytes | None, str | None, str | None] | BaseException] = []
            pending_futures = [asyncio.ensure_future(t) for t in tasks]

            last_emit_time = asyncio.get_event_loop().time()
            stage_start_time = asyncio.get_event_loop().time()

            global_timeout_triggered = False

            while pending_futures:
                # Check global timeout - if exceeded, cancel remaining and move on
                elapsed = asyncio.get_event_loop().time() - stage_start_time
                if elapsed > PNG_STAGE_TIMEOUT and not global_timeout_triggered:
                    logger.warning(f"PNG stage global timeout after {elapsed:.1f}s - cancelling {len(pending_futures)} remaining tasks")
                    global_timeout_triggered = True
                    # Cancel all remaining tasks (they'll raise CancelledError)
                    for fut in pending_futures:
                        fut.cancel()
                    # Don't break - let the loop collect the cancelled results

                # Wait for at least one task to complete (with timeout for heartbeat)
                done, pending_futures_set = await asyncio.wait(
                    pending_futures,
                    timeout=0.5,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                pending_futures = list(pending_futures_set)

                # Process completed tasks
                for fut in done:
                    completed += 1
                    try:
                        results.append(fut.result())
                    except asyncio.CancelledError:
                        # Task was cancelled due to global timeout
                        # We don't know which page this was, but we'll handle missing pages later
                        logger.warning(f"Task {completed} was cancelled due to timeout")
                        results.append(Exception("Global timeout - task cancelled"))
                    except Exception as e:
                        # Store exception as result (mimics return_exceptions=True)
                        results.append(e)

                # Emit progress
                current_time = asyncio.get_event_loop().time()
                if done:
                    yield f"data: {json.dumps({'stage': 'png', 'current': completed, 'total': total})}\n\n"
                    last_emit_time = current_time
                elif current_time - last_emit_time > 3:
                    yield ": heartbeat\n\n"
                    last_emit_time = current_time

            # Final PNG progress event
            yield f"data: {json.dumps({'stage': 'png', 'current': total, 'total': total})}\n\n"

            # Track successes and failures (no longer need to store PNG bytes)
            successful_pages: list[tuple[str, str]] = []  # (page_id, storage_path)
            failed_page_ids: list[str] = []

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    page_id = page_data_list[i]["id"]
                    logger.error(f"PNG task exception for page {page_id}: {result}")
                    failed_page_ids.append(page_id)
                else:
                    page_id, png_bytes, storage_path, error = result
                    if png_bytes and storage_path:
                        successful_pages.append((page_id, storage_path))
                    elif error:
                        logger.warning(f"Page {page_id} PNG failed: {error}")
                        failed_page_ids.append(page_id)

            # Emit failures event if any
            if failed_page_ids:
                yield f"data: {json.dumps({'stage': 'png_failures', 'pageIds': failed_page_ids})}\n\n"

            # ============================================================
            # Batch DB update for successful PNG renders
            # ============================================================
            if successful_pages:
                with SessionLocal() as db:
                    for page_id, storage_path in successful_pages:
                        db.query(Page).filter(Page.id == page_id).update({
                            "page_image_path": storage_path,
                            "page_image_ready": True
                        })
                    db.commit()
                    logger.info(f"Batch updated {len(successful_pages)} pages with PNG paths")

            # Clear PDF cache to free memory
            pdf_cache.clear()
            logger.info("PDF cache cleared")

        except Exception as e:
            logger.error(f"PNG stage failed: {e}")
            yield f"data: {json.dumps({'stage': 'error', 'message': str(e)})}\n\n"
            return

        # ============================================================
        # Complete - app is immediately usable after PNG stage
        # OCR+AI can be added later as background jobs or on-demand
        # ============================================================
        yield f"data: {json.dumps({'stage': 'complete'})}\n\n"

        logger.info(
            f"Stream processing complete for project {project_id}: {total} pages"
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/projects/{project_id}/reprocess-ocr-ai-stream")
async def reprocess_ocr_ai_stream(
    project_id: str,
    # NOTE: Intentionally NOT using Depends(get_db) - SSE runs too long
):
    """
    SSE endpoint that reprocesses OCR+AI for pages that have PNGs but weren't processed.

    This is useful when the initial processing was interrupted (e.g., timeout).
    Only processes pages where page_image_ready=true but processed_pass_1=false.

    SSE events:
    - {"stage": "init", "pageCount": N}
    - {"stage": "ocr", "current": N, "total": T}
    - {"stage": "ai", "current": N, "total": T}
    - {"stage": "complete"}
    - {"stage": "error", "message": "..."}

    Heartbeat comment sent every 3 seconds to prevent connection timeout.
    """
    # Extract page data before SSE starts
    page_data_list: list[dict] = []

    with SessionLocal() as db:
        # Verify project exists
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Get pages with PNGs but no AI processing
        pages = (
            db.query(Page)
            .join(Discipline)
            .filter(
                Discipline.project_id == project_id,
                Page.page_image_ready == True,  # noqa: E712
                Page.processed_pass_1 == False,  # noqa: E712
            )
            .all()
        )

        # Extract to simple dicts before session closes
        page_data_list = [
            {"id": str(p.id), "page_image_path": p.page_image_path}
            for p in pages
        ]

    total = len(page_data_list)

    async def event_generator() -> AsyncGenerator[str, None]:
        # Emit init event with page count
        yield f"data: {json.dumps({'stage': 'init', 'pageCount': total})}\n\n"

        if total == 0:
            yield f"data: {json.dumps({'stage': 'complete'})}\n\n"
            return

        last_emit_time = asyncio.get_event_loop().time()

        for i, page_data in enumerate(page_data_list):
            page_id = page_data["id"]
            page_image_path = page_data["page_image_path"]

            # Download PNG from storage
            try:
                png_bytes = await download_file(page_image_path)
                logger.info(f"Downloaded PNG for page {page_id}")
            except Exception as e:
                logger.error(f"Failed to download PNG for page {page_id}: {e}")
                # Emit progress and continue to next page
                yield f"data: {json.dumps({'stage': 'ocr', 'current': i + 1, 'total': total})}\n\n"
                yield f"data: {json.dumps({'stage': 'ai', 'current': i + 1, 'total': total})}\n\n"
                continue

            # --- OCR ---
            full_text = ""
            ocr_spans = []
            try:
                full_text, ocr_spans = await extract_full_page_text(png_bytes)

                # Save OCR results with short-lived session
                with SessionLocal() as ocr_db:
                    ocr_db.query(Page).filter(Page.id == page_id).update({
                        "full_page_text": full_text,
                        "ocr_data": ocr_spans,
                        "processed_ocr": True
                    })
                    ocr_db.commit()

                logger.info(f"OCR complete for page {page_id}: {len(ocr_spans)} spans")

            except Exception as e:
                logger.error(f"OCR failed for page {page_id}: {e}")
                # Continue with empty text/spans

            # Emit OCR progress
            yield f"data: {json.dumps({'stage': 'ocr', 'current': i + 1, 'total': total})}\n\n"
            last_emit_time = asyncio.get_event_loop().time()

            # --- AI Pass 1 ---
            try:
                initial_context = await analyze_page_pass_1(
                    image_bytes=png_bytes,
                    ocr_text=full_text,
                    ocr_spans=ocr_spans,
                )

                # Save AI results with short-lived session
                with SessionLocal() as ai_db:
                    ai_db.query(Page).filter(Page.id == page_id).update({
                        "initial_context": initial_context,
                        "processed_pass_1": True
                    })
                    ai_db.commit()

                logger.info(f"AI Pass 1 complete for page {page_id}")

            except Exception as e:
                logger.error(f"AI failed for page {page_id}: {e}")
                # Continue to next page - don't set processed_pass_1

            # Emit AI progress
            yield f"data: {json.dumps({'stage': 'ai', 'current': i + 1, 'total': total})}\n\n"

            # Heartbeat if processing is slow
            current_time = asyncio.get_event_loop().time()
            if current_time - last_emit_time > 3:
                yield ": heartbeat\n\n"
            last_emit_time = current_time

        # Complete
        yield f"data: {json.dumps({'stage': 'complete'})}\n\n"

        logger.info(
            f"Reprocessing complete for project {project_id}: {total} pages"
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/pages/{page_id}/retry-png")
async def retry_page_png(
    page_id: str,
    db: Session = Depends(get_db),
):
    """
    Retry PNG rendering for a single page that previously failed.

    Returns:
        {"success": true, "pageImagePath": "..."} on success
        {"success": false, "error": "..."} on failure
    """
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    # Get project_id from discipline
    discipline = db.query(Discipline).filter(Discipline.id == page.discipline_id).first()
    if not discipline:
        raise HTTPException(status_code=404, detail="Discipline not found")

    project_id = discipline.project_id

    # Download PDF first
    try:
        pdf_bytes = await download_file(page.file_path)
    except Exception as e:
        return {"success": False, "error": f"Failed to download PDF: {e}"}

    # Render PNG (use page.page_index for multi-page PDFs)
    result_page_id, png_bytes, storage_path, error = await _render_page_png(
        page_id, project_id, pdf_bytes, page.page_index
    )

    if png_bytes and storage_path:
        # Update DB with the new storage path
        page.page_image_path = storage_path
        page.page_image_ready = True
        db.commit()
        return {"success": True, "pageImagePath": storage_path}
    else:
        return {"success": False, "error": error or "Unknown error"}


# =============================================================================
# Brain Mode: Sheet-analyzer processing endpoints
# =============================================================================

from app.models.processing_job import ProcessingJob
from app.services.processing_job import (
    create_job_queue,
    get_active_job_for_project,
    process_project_pages,
    sse_event_generator,
    start_processing_job,
)


@router.post("/projects/{project_id}/process")
async def start_project_processing(
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    Start background processing of all pages in a project.

    This creates a processing job that runs the sheet-analyzer pipeline
    on each page. Processing continues even if the browser closes.

    Returns:
        {"job_id": "...", "total_pages": N, "status": "pending"}
    """
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check for existing active job
    existing_job = get_active_job_for_project(project_id, db)
    if existing_job:
        return {
            "job_id": existing_job.id,
            "total_pages": existing_job.total_pages,
            "processed_pages": existing_job.processed_pages,
            "status": existing_job.status,
            "message": "Processing already in progress",
        }

    # Create new job
    job = start_processing_job(project_id, db)

    # Create event queue and start background task
    create_job_queue(job.id)
    asyncio.create_task(process_project_pages(job.id))

    return {
        "job_id": job.id,
        "total_pages": job.total_pages,
        "status": job.status,
    }


@router.get("/projects/{project_id}/process/stream")
async def stream_project_processing(
    project_id: str,
):
    """
    SSE endpoint for streaming processing progress updates.

    Connects to the active processing job for a project (if any)
    and streams events as pages are processed.

    SSE events:
    - {"type": "init", "status": "...", "total_pages": N, "processed_pages": M}
    - {"type": "page_started", "page_id": "...", "page_name": "...", "current": N, "total": T}
    - {"type": "page_completed", "page_id": "...", "page_name": "...", "details": [...]}
    - {"type": "page_failed", "page_id": "...", "error": "..."}
    - {"type": "job_completed", "processed_pages": N, "total_pages": T}
    - {"type": "job_failed", "error": "..."}

    Heartbeat comment sent every 3 seconds to prevent connection timeout.
    """
    # Find active job for project
    with SessionLocal() as db:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        job = get_active_job_for_project(project_id, db)
        if not job:
            # Check for most recent completed job
            job = (
                db.query(ProcessingJob)
                .filter(ProcessingJob.project_id == project_id)
                .order_by(ProcessingJob.created_at.desc())
                .first()
            )
            if not job:
                raise HTTPException(status_code=404, detail="No processing job found")

        job_id = job.id

    return StreamingResponse(
        sse_event_generator(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/projects/{project_id}/process/status")
async def get_processing_status(
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    Get current processing status for a project.

    Returns:
        {"status": "...", "job_id": "...", "total_pages": N, "processed_pages": M, ...}
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check for active job
    job = get_active_job_for_project(project_id, db)
    if job:
        return {
            "status": job.status,
            "job_id": job.id,
            "total_pages": job.total_pages,
            "processed_pages": job.processed_pages,
            "current_page_name": job.current_page_name,
            "started_at": job.started_at.isoformat() if job.started_at else None,
        }

    # Check for most recent completed job
    job = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.project_id == project_id)
        .order_by(ProcessingJob.created_at.desc())
        .first()
    )

    if job:
        return {
            "status": job.status,
            "job_id": job.id,
            "total_pages": job.total_pages,
            "processed_pages": job.processed_pages,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error_message": job.error_message,
        }

    return {
        "status": "none",
        "message": "No processing jobs found for this project",
    }
