"""Processing endpoints for page analysis."""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
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


async def _render_page_png(
    page: Page,
    project_id: str,
    pdf_cache: dict[str, bytes],
) -> tuple[str, bytes | None, str | None]:
    """
    Render PDF page to PNG and upload to storage.

    Returns:
        (page_id, png_bytes, error_message)
        png_bytes is None if rendering failed
    """
    page_id = str(page.id)
    try:
        # Download PDF if not cached
        if page.file_path not in pdf_cache:
            pdf_cache[page.file_path] = await download_file(page.file_path)

        pdf_bytes = pdf_cache[page.file_path]

        # Render to PNG at 150 DPI
        png_bytes = await asyncio.to_thread(pdf_page_to_image, pdf_bytes, 0, 150)

        # Upload to storage
        storage_path = await upload_page_image(png_bytes, project_id, page_id)

        # Update database
        with SessionLocal() as db:
            page_record = db.query(Page).filter(Page.id == page_id).first()
            if page_record:
                page_record.page_image_path = storage_path
                page_record.page_image_ready = True
                db.commit()

        logger.info(f"PNG complete for page {page_id}")
        return page_id, png_bytes, None

    except Exception as e:
        logger.error(f"PNG failed for page {page_id}: {e}")
        return page_id, None, str(e)


@router.post("/projects/{project_id}/process-uploads-stream")
async def process_uploads_stream(
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    SSE endpoint that streams progress updates as processing happens.

    Pipeline:
    1. PNG stage (parallel): Render all pages to PNG, upload to storage
    2. OCR+AI stage (sequential): For each page, run Tesseract → Gemini → save

    SSE events:
    - {"stage": "png", "current": N, "total": T}
    - {"stage": "ocr", "current": N, "total": T}
    - {"stage": "ai", "current": N, "total": T}
    - {"stage": "complete"}
    - {"stage": "error", "message": "..."}

    Heartbeat comment sent every 3 seconds to prevent connection timeout.
    """
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get all unprocessed pages
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

    total = len(pages)

    async def event_generator() -> AsyncGenerator[str, None]:
        if total == 0:
            yield f"data: {json.dumps({'stage': 'complete'})}\n\n"
            return

        # PDF cache for reuse across stages
        pdf_cache: dict[str, bytes] = {}

        # Progress tracking
        png_progress = {"current": 0}

        # Semaphore for PNG concurrency (max 5)
        semaphore = asyncio.Semaphore(5)

        # ============================================================
        # Stage 1: PNG rendering (parallel)
        # ============================================================
        async def render_with_tracking(page: Page) -> tuple[str, bytes | None, str | None]:
            async with semaphore:
                result = await _render_page_png(page, project_id, pdf_cache)
                png_progress["current"] += 1
                return result

        # Launch all PNG tasks
        tasks = [asyncio.create_task(render_with_tracking(p)) for p in pages]

        # Yield progress while PNG tasks complete
        last_emit_time = asyncio.get_event_loop().time()
        last_current = 0

        while not all(t.done() for t in tasks):
            await asyncio.sleep(0.3)
            current_time = asyncio.get_event_loop().time()

            if png_progress["current"] != last_current:
                yield f"data: {json.dumps({'stage': 'png', 'current': png_progress['current'], 'total': total})}\n\n"
                last_current = png_progress["current"]
                last_emit_time = current_time
            elif current_time - last_emit_time > 3:
                yield ": heartbeat\n\n"
                last_emit_time = current_time

        # Collect PNG results
        png_results: list[tuple[str, bytes | None, str | None]] = [t.result() for t in tasks]

        # Final PNG progress event
        yield f"data: {json.dumps({'stage': 'png', 'current': total, 'total': total})}\n\n"

        # Build map of page_id -> png_bytes for OCR+AI stage
        page_png_map: dict[str, bytes] = {}
        for page_id, png_bytes, error in png_results:
            if png_bytes:
                page_png_map[page_id] = png_bytes
            elif error:
                logger.warning(f"Page {page_id} PNG failed: {error}")

        # ============================================================
        # Stage 2: OCR + AI (sequential per page)
        # ============================================================
        last_emit_time = asyncio.get_event_loop().time()

        for i, page in enumerate(pages):
            page_id = str(page.id)
            png_bytes = page_png_map.get(page_id)

            if not png_bytes:
                logger.warning(f"Skipping OCR+AI for page {page_id}: no PNG available")
                continue

            # --- OCR ---
            try:
                full_text, ocr_spans = await extract_full_page_text(png_bytes)

                # Save OCR results
                with SessionLocal() as ocr_db:
                    page_record = ocr_db.query(Page).filter(Page.id == page_id).first()
                    if page_record:
                        page_record.full_page_text = full_text
                        page_record.ocr_data = ocr_spans
                        page_record.processed_ocr = True
                        ocr_db.commit()

                logger.info(f"OCR complete for page {page_id}: {len(ocr_spans)} spans")

            except Exception as e:
                logger.error(f"OCR failed for page {page_id}: {e}")
                full_text = ""
                ocr_spans = []

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

                # Save AI results
                with SessionLocal() as ai_db:
                    page_record = ai_db.query(Page).filter(Page.id == page_id).first()
                    if page_record:
                        page_record.initial_context = initial_context
                        page_record.processed_pass_1 = True
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
