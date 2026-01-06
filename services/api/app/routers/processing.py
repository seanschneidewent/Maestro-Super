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
from app.services.gemini import analyze_page_pass_1
from app.services.ocr import extract_full_page_text
from app.services.pdf_renderer import pdf_page_to_image
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
) -> tuple[str, bytes | None, str | None, str | None]:
    """
    Render PDF page to PNG and upload to storage.

    Args:
        page_id: Page ID string
        project_id: Project ID for storage path
        pdf_bytes: PDF bytes for this page

    Returns:
        (page_id, png_bytes, storage_path, error_message)
        png_bytes/storage_path is None if rendering failed
    """
    try:
        # Render to PNG at 150 DPI with 30s timeout
        png_bytes = await asyncio.wait_for(
            asyncio.to_thread(pdf_page_to_image, pdf_bytes, 0, 150),
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
    3. OCR+AI stage (sequential): For each page, run Tesseract → Gemini → save

    SSE events:
    - {"stage": "init", "pageCount": N}  (after bulk insert)
    - {"stage": "png", "current": N, "total": T}
    - {"stage": "png_failures", "pageIds": [...]}  (list of failed page IDs)
    - {"stage": "ocr", "current": N, "total": T}
    - {"stage": "ai", "current": N, "total": T}
    - {"stage": "complete"}
    - {"stage": "error", "message": "..."}

    Heartbeat comment sent every 3 seconds to prevent connection timeout.
    """
    # Use manual session management - quick open/close, don't hold for SSE duration
    # Extract page data to dicts so we can close session before SSE starts
    page_data_list: list[dict] = []

    with SessionLocal() as db:
        # Verify project exists
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Bulk insert disciplines/pages if request body provided
        if request and request.disciplines:
            for disc_data in request.disciplines:
                discipline = Discipline(
                    project_id=project_id,
                    name=disc_data.code,
                    display_name=disc_data.display_name,
                )
                db.add(discipline)
                db.flush()  # Get ID without committing

                for page_input in disc_data.pages:
                    page = Page(
                        discipline_id=str(discipline.id),
                        page_name=page_input.page_name,
                        file_path=page_input.storage_path,
                    )
                    db.add(page)

            db.commit()
            logger.info(f"Bulk inserted {len(request.disciplines)} disciplines for project {project_id}")

        # Get all unprocessed pages and extract to dicts (detach from ORM)
        pages = (
            db.query(Page)
            .join(Discipline)
            .filter(
                Discipline.project_id == project_id,
                (Page.page_image_ready == False)  # noqa: E712
                | (Page.processed_ocr == False)  # noqa: E712
                | (Page.processed_pass_1 == False),  # noqa: E712
            )
            .all()
        )

        # Extract to simple dicts before session closes
        page_data_list = [
            {"id": str(p.id), "file_path": p.file_path}
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
        # Stage 1: PNG rendering (parallel)
        # ============================================================
        try:
            async def render_with_semaphore(page_data: dict) -> tuple[str, bytes | None, str | None, str | None]:
                try:
                    pdf_bytes = await get_pdf_bytes(page_data["file_path"])
                except Exception as e:
                    return page_data["id"], None, None, f"PDF download failed: {e}"
                async with semaphore:
                    return await _render_page_png(page_data["id"], project_id, pdf_bytes)

            # Use asyncio.gather with return_exceptions=True to prevent stream crash
            # Run tasks and emit progress periodically
            tasks = [render_with_semaphore(p) for p in page_data_list]

            # Track progress with a wrapper that updates on completion
            completed = 0
            results: list[tuple[str, bytes | None, str | None, str | None] | BaseException] = []
            pending_futures = [asyncio.ensure_future(t) for t in tasks]

            last_emit_time = asyncio.get_event_loop().time()

            while pending_futures:
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

            # Build map of page_id -> png_bytes, track failures and successful paths
            page_png_map: dict[str, bytes] = {}
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
                        page_png_map[page_id] = png_bytes
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

            # Clear PDF cache to free memory before OCR stage
            pdf_cache.clear()
            logger.info("PDF cache cleared to free memory")

        except Exception as e:
            logger.error(f"PNG stage failed: {e}")
            yield f"data: {json.dumps({'stage': 'error', 'message': str(e)})}\n\n"
            return

        # ============================================================
        # Stage 2: OCR + AI (sequential per page)
        # Uses short-lived DB sessions per page to avoid connection timeout
        # ============================================================
        last_emit_time = asyncio.get_event_loop().time()

        for i, page_data in enumerate(page_data_list):
            page_id = page_data["id"]
            png_bytes = page_png_map.get(page_id)

            if not png_bytes:
                logger.warning(f"Skipping OCR+AI for page {page_id}: no PNG available")
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

        # ============================================================
        # Complete
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

    # Render PNG
    result_page_id, png_bytes, storage_path, error = await _render_page_png(
        page_id, project_id, pdf_bytes
    )

    if png_bytes and storage_path:
        # Update DB with the new storage path
        page.page_image_path = storage_path
        page.page_image_ready = True
        db.commit()
        return {"success": True, "pageImagePath": storage_path}
    else:
        return {"success": False, "error": error or "Unknown error"}
