"""
PNG Rendering Job Service - Background job system for PDF to PNG conversion.

Handles:
- Starting PNG rendering jobs that survive page refresh
- Processing pages in parallel with progress tracking
- SSE event emission for live progress updates

Status flow: pending -> processing -> completed/failed
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import AsyncGenerator, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.discipline import Discipline
from app.models.page import Page
from app.models.processing_job import ProcessingJob
from app.models.project import Project
from app.services.pdf_renderer import get_pdf_page_count, pdf_page_to_image
from app.services.storage import download_file, upload_page_image

logger = logging.getLogger(__name__)


class UUIDEncoder(json.JSONEncoder):
    """JSON encoder that handles UUID objects."""
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        return super().default(obj)


# Global dict to track active PNG jobs and their event queues
# Key: job_id, Value: asyncio.Queue for SSE events
_active_png_jobs: dict[str, asyncio.Queue] = {}


def get_png_job_queue(job_id: str) -> Optional[asyncio.Queue]:
    """Get the event queue for an active PNG job."""
    return _active_png_jobs.get(job_id)


def create_png_job_queue(job_id: str) -> asyncio.Queue:
    """Create and register an event queue for a PNG job."""
    queue = asyncio.Queue()
    _active_png_jobs[job_id] = queue
    return queue


def remove_png_job_queue(job_id: str):
    """Remove the event queue for a completed PNG job."""
    _active_png_jobs.pop(job_id, None)


async def emit_png_event(job_id: str, event: dict):
    """Emit an event to the PNG job's SSE queue."""
    queue = _active_png_jobs.get(job_id)
    if queue:
        await queue.put(event)


def start_png_rendering_job(project_id: str, db: Session) -> ProcessingJob:
    """
    Create a new PNG rendering job for a project.

    Args:
        project_id: Project ID to process
        db: Database session

    Returns:
        Created ProcessingJob instance with job_type='png_rendering'
    """
    # Count pages needing PNG rendering
    total_pages = (
        db.query(Page)
        .join(Discipline)
        .filter(
            Discipline.project_id == project_id,
            Page.page_image_ready == False,  # noqa: E712
        )
        .count()
    )

    # Create job record
    job = ProcessingJob(
        project_id=project_id,
        job_type="png_rendering",
        status="pending",
        total_pages=total_pages,
        processed_pages=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    logger.info(f"Created PNG rendering job {job.id} for project {project_id} with {total_pages} pages")
    return job


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


async def process_png_rendering(job_id: str):
    """
    Background task that renders all pages to PNG.

    This runs independently of the HTTP request - rendering continues
    even if the browser closes.

    Args:
        job_id: ProcessingJob ID to process
    """
    # Mark job as processing
    with SessionLocal() as db:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if not job:
            logger.error(f"PNG job {job_id} not found")
            return

        job.status = "processing"
        job.started_at = datetime.utcnow()
        db.commit()

        project_id = job.project_id

    await emit_png_event(job_id, {"type": "job_started", "job_id": job_id})

    # Get all pages needing PNG rendering
    with SessionLocal() as db:
        pages = (
            db.query(Page)
            .join(Discipline)
            .filter(
                Discipline.project_id == project_id,
                Page.page_image_ready == False,  # noqa: E712
            )
            .all()
        )

        # Extract page data before session closes
        page_data_list = [
            {"id": str(p.id), "file_path": p.file_path, "page_index": p.page_index}
            for p in pages
        ]

    total_pages = len(page_data_list)

    if total_pages == 0:
        # No pages to process
        with SessionLocal() as db:
            job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
            if job:
                job.status = "completed"
                job.completed_at = datetime.utcnow()
                db.commit()

        await emit_png_event(job_id, {
            "type": "job_completed",
            "job_id": job_id,
            "processed_pages": 0,
            "total_pages": 0,
        })
        await asyncio.sleep(2)
        remove_png_job_queue(job_id)
        return

    # PDF download with lock (prevents race condition + memory bloat)
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

    # Global timeout for entire PNG stage
    PNG_STAGE_TIMEOUT = 300  # 5 minutes

    try:
        tasks = [render_with_semaphore(p) for p in page_data_list]
        completed = 0
        results: list[tuple[str, bytes | None, str | None, str | None] | BaseException] = []
        pending_futures = [asyncio.ensure_future(t) for t in tasks]

        stage_start_time = asyncio.get_event_loop().time()
        global_timeout_triggered = False

        while pending_futures:
            # Check global timeout
            elapsed = asyncio.get_event_loop().time() - stage_start_time
            if elapsed > PNG_STAGE_TIMEOUT and not global_timeout_triggered:
                logger.warning(f"PNG job {job_id} global timeout after {elapsed:.1f}s - cancelling {len(pending_futures)} remaining tasks")
                global_timeout_triggered = True
                for fut in pending_futures:
                    fut.cancel()

            # Wait for tasks with timeout
            done, pending_futures_set = await asyncio.wait(
                pending_futures,
                timeout=1.0,
                return_when=asyncio.FIRST_COMPLETED,
            )
            pending_futures = list(pending_futures_set)

            # Process completed tasks
            for fut in done:
                completed += 1
                try:
                    results.append(fut.result())
                except asyncio.CancelledError:
                    logger.warning(f"PNG task {completed} was cancelled due to timeout")
                    results.append(Exception("Global timeout - task cancelled"))
                except Exception as e:
                    results.append(e)

            # Update job progress and emit event
            if done:
                with SessionLocal() as db:
                    db.query(ProcessingJob).filter(ProcessingJob.id == job_id).update({
                        "processed_pages": completed
                    })
                    db.commit()

                await emit_png_event(job_id, {
                    "type": "png_progress",
                    "current": completed,
                    "total": total_pages,
                })

        # Track successes and failures
        successful_pages: list[tuple[str, str]] = []
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

        # Batch DB update for successful PNG renders
        if successful_pages:
            with SessionLocal() as db:
                for page_id, storage_path in successful_pages:
                    db.query(Page).filter(Page.id == page_id).update({
                        "page_image_path": storage_path,
                        "page_image_ready": True
                    })
                db.commit()
                logger.info(f"Batch updated {len(successful_pages)} pages with PNG paths")

        # Emit failures event if any
        if failed_page_ids:
            await emit_png_event(job_id, {
                "type": "png_failures",
                "page_ids": failed_page_ids,
            })

        # Mark job as completed
        with SessionLocal() as db:
            job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
            if job:
                job.status = "completed"
                job.completed_at = datetime.utcnow()
                job.processed_pages = len(successful_pages)
                db.commit()

        await emit_png_event(job_id, {
            "type": "job_completed",
            "job_id": job_id,
            "processed_pages": len(successful_pages),
            "total_pages": total_pages,
            "failed_count": len(failed_page_ids),
        })

        # Clear PDF cache
        pdf_cache.clear()
        logger.info(f"PNG job {job_id} completed: {len(successful_pages)}/{total_pages} pages rendered")

    except Exception as e:
        logger.error(f"PNG job {job_id} failed: {e}")
        with SessionLocal() as db:
            job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
            if job:
                job.status = "failed"
                job.error_message = str(e)
                db.commit()

        await emit_png_event(job_id, {
            "type": "job_failed",
            "job_id": job_id,
            "error": str(e),
        })

    # Clean up queue after delay
    await asyncio.sleep(5)
    remove_png_job_queue(job_id)


async def sse_png_event_generator(job_id: str) -> AsyncGenerator[str, None]:
    """
    Generate SSE events for a PNG rendering job.

    Args:
        job_id: ProcessingJob ID to stream events for

    Yields:
        SSE-formatted event strings
    """
    # Get or create queue for this job
    queue = get_png_job_queue(job_id)
    if not queue:
        queue = create_png_job_queue(job_id)

    # Check if job exists and get initial state
    with SessionLocal() as db:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if not job:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Job not found'}, cls=UUIDEncoder)}\n\n"
            return

        # Send initial state
        yield f"data: {json.dumps({'type': 'init', 'status': job.status, 'total_pages': job.total_pages, 'processed_pages': job.processed_pages}, cls=UUIDEncoder)}\n\n"

        # If job is already completed, send completion event
        if job.status == "completed":
            yield f"data: {json.dumps({'type': 'job_completed', 'job_id': job_id, 'processed_pages': job.processed_pages, 'total_pages': job.total_pages}, cls=UUIDEncoder)}\n\n"
            return
        elif job.status == "failed":
            yield f"data: {json.dumps({'type': 'job_failed', 'error': job.error_message}, cls=UUIDEncoder)}\n\n"
            return

    # Stream events from queue
    while True:
        try:
            # Wait for event with timeout for heartbeat
            event = await asyncio.wait_for(queue.get(), timeout=3.0)
            yield f"data: {json.dumps(event, cls=UUIDEncoder)}\n\n"

            # Check for terminal events
            if event.get("type") in ("job_completed", "job_failed"):
                break

        except asyncio.TimeoutError:
            # Send heartbeat
            yield ": heartbeat\n\n"

            # Check if job is still active
            with SessionLocal() as db:
                job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
                if job and job.status in ("completed", "failed"):
                    if job.status == "completed":
                        yield f"data: {json.dumps({'type': 'job_completed', 'job_id': job_id, 'processed_pages': job.processed_pages, 'total_pages': job.total_pages}, cls=UUIDEncoder)}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'job_failed', 'error': job.error_message}, cls=UUIDEncoder)}\n\n"
                    break


def get_active_png_job_for_project(project_id: str, db: Session) -> Optional[ProcessingJob]:
    """Get the active PNG rendering job for a project, if any."""
    return (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.project_id == project_id,
            ProcessingJob.job_type == "png_rendering",
            ProcessingJob.status.in_(["pending", "processing"]),
        )
        .first()
    )
