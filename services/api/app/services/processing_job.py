"""
Processing Job Service - Background job system for sheet-analyzer pipeline.

Handles:
- Starting processing jobs
- Processing pages sequentially with progress tracking
- Pause/resume functionality
- Updating job status
- SSE event emission for live progress updates

Status flow: pending -> processing -> completed/failed/paused
"""

import asyncio
import json
import logging
from datetime import datetime
from io import BytesIO
from typing import AsyncGenerator, Callable, Optional
from uuid import UUID

from PIL import Image
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.session import SessionLocal
from app.models.discipline import Discipline
from app.models.page import Page
from app.models.processing_job import ProcessingJob
from app.models.project import Project
from app.services.detail_parser import parse_context_markdown
from app.services.sheet_analyzer import process_page
from app.services.storage import download_file

logger = logging.getLogger(__name__)


class UUIDEncoder(json.JSONEncoder):
    """JSON encoder that handles UUID objects."""
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        return super().default(obj)


# Global dict to track active jobs and their event queues
# Key: job_id, Value: asyncio.Queue for SSE events
_active_jobs: dict[str, asyncio.Queue] = {}


def get_job_queue(job_id: str) -> Optional[asyncio.Queue]:
    """Get the event queue for an active job."""
    return _active_jobs.get(job_id)


def create_job_queue(job_id: str) -> asyncio.Queue:
    """Create and register an event queue for a job."""
    queue = asyncio.Queue()
    _active_jobs[job_id] = queue
    return queue


def remove_job_queue(job_id: str):
    """Remove the event queue for a completed job."""
    _active_jobs.pop(job_id, None)


async def emit_event(job_id: str, event: dict):
    """Emit an event to the job's SSE queue."""
    queue = _active_jobs.get(job_id)
    if queue:
        await queue.put(event)


def start_processing_job(project_id: str, db: Session) -> ProcessingJob:
    """
    Create a new processing job for a project.

    Args:
        project_id: Project ID to process
        db: Database session

    Returns:
        Created ProcessingJob instance
    """
    # Count total pages in project
    total_pages = (
        db.query(Page)
        .join(Discipline)
        .filter(
            Discipline.project_id == project_id,
            Page.page_image_ready == True,  # noqa: E712
            Page.processing_status == "pending",
        )
        .count()
    )

    # Create job record
    job = ProcessingJob(
        project_id=project_id,
        status="pending",
        total_pages=total_pages,
        processed_pages=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    logger.info(f"Created processing job {job.id} for project {project_id} with {total_pages} pages")
    return job


async def process_project_pages(job_id: str):
    """
    Background task that processes all pages in a project.

    This runs independently of the HTTP request - processing continues
    even if the browser closes.

    Args:
        job_id: ProcessingJob ID to process
    """
    settings = get_settings()
    api_key = settings.gemini_api_key

    if not api_key:
        logger.error("No Gemini API key configured")
        with SessionLocal() as db:
            job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
            if job:
                job.status = "failed"
                job.error_message = "No Gemini API key configured"
                db.commit()
        await emit_event(job_id, {"type": "job_failed", "error": "No Gemini API key configured"})
        remove_job_queue(job_id)
        return

    # Mark job as processing
    with SessionLocal() as db:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        job.status = "processing"
        job.started_at = datetime.utcnow()
        db.commit()

        project_id = job.project_id

    await emit_event(job_id, {"type": "job_started", "job_id": job_id})

    # Get all pages to process
    with SessionLocal() as db:
        pages = (
            db.query(Page)
            .join(Discipline)
            .filter(
                Discipline.project_id == project_id,
                Page.page_image_ready == True,  # noqa: E712
                Page.processing_status == "pending",
            )
            .order_by(Discipline.name, Page.page_name)
            .all()
        )

        # Extract page data before session closes
        page_data_list = [
            {
                "id": str(p.id),
                "page_name": p.page_name,
                "page_image_path": p.page_image_path,
            }
            for p in pages
        ]

    total_pages = len(page_data_list)
    processed_count = 0

    for page_data in page_data_list:
        # Check if job was paused before processing next page
        with SessionLocal() as db:
            job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
            if job and job.status == "paused":
                logger.info(f"[{job_id}] Job paused at page {processed_count}/{total_pages}")
                await emit_event(job_id, {
                    "type": "job_paused",
                    "job_id": job_id,
                    "processed_pages": processed_count,
                    "total_pages": total_pages,
                })
                # Exit the processing loop - job can be resumed later
                remove_job_queue(job_id)
                return

        page_id = page_data["id"]
        page_name = page_data["page_name"]
        page_image_path = page_data["page_image_path"]

        logger.info(f"[{job_id}] Processing page {processed_count + 1}/{total_pages}: {page_name}")

        # Update job with current page
        with SessionLocal() as db:
            job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
            if job:
                job.current_page_id = page_id
                job.current_page_name = page_name
                db.commit()

        await emit_event(job_id, {
            "type": "page_started",
            "page_id": page_id,
            "page_name": page_name,
            "current": processed_count + 1,
            "total": total_pages,
        })

        # Mark page as processing
        with SessionLocal() as db:
            db.query(Page).filter(Page.id == page_id).update({
                "processing_status": "processing"
            })
            db.commit()

        try:
            # Download page image
            png_bytes = await download_file(page_image_path)
            image = Image.open(BytesIO(png_bytes))
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Run sheet-analyzer pipeline
            result = await process_page(image, api_key, page_name)

            # Parse details from markdown
            details = parse_context_markdown(result["context_markdown"])

            # Save results to database
            with SessionLocal() as db:
                db.query(Page).filter(Page.id == page_id).update({
                    "semantic_index": result["semantic_index"],
                    "context_markdown": result["context_markdown"],
                    "details": details,
                    "processing_status": "completed",
                    "processed_at": datetime.utcnow(),
                })
                db.commit()

            processed_count += 1

            # Update job progress
            with SessionLocal() as db:
                job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
                if job:
                    job.processed_pages = processed_count
                    db.commit()

            await emit_event(job_id, {
                "type": "page_completed",
                "page_id": page_id,
                "page_name": page_name,
                "details": details,
                "current": processed_count,
                "total": total_pages,
            })

            logger.info(f"[{job_id}] Completed page {page_name}: {len(details)} details extracted")

        except Exception as e:
            logger.error(f"[{job_id}] Failed to process page {page_name}: {e}")

            # Mark page as failed
            with SessionLocal() as db:
                db.query(Page).filter(Page.id == page_id).update({
                    "processing_status": "failed"
                })
                db.commit()

            await emit_event(job_id, {
                "type": "page_failed",
                "page_id": page_id,
                "page_name": page_name,
                "error": str(e),
                "current": processed_count,
                "total": total_pages,
            })

            # Continue to next page instead of failing entire job
            continue

    # Mark job as completed
    with SessionLocal() as db:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if job:
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            job.current_page_id = None
            job.current_page_name = None
            db.commit()

    await emit_event(job_id, {
        "type": "job_completed",
        "job_id": job_id,
        "processed_pages": processed_count,
        "total_pages": total_pages,
    })

    logger.info(f"[{job_id}] Job completed: {processed_count}/{total_pages} pages processed")

    # Clean up queue after a delay (allow SSE clients to receive final event)
    await asyncio.sleep(5)
    remove_job_queue(job_id)


async def sse_event_generator(job_id: str) -> AsyncGenerator[str, None]:
    """
    Generate SSE events for a processing job.

    Args:
        job_id: ProcessingJob ID to stream events for

    Yields:
        SSE-formatted event strings
    """
    # Get or create queue for this job
    queue = get_job_queue(job_id)
    if not queue:
        queue = create_job_queue(job_id)

    # Check if job exists and get initial state
    with SessionLocal() as db:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if not job:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Job not found'}, cls=UUIDEncoder)}\n\n"
            return

        # Send initial state
        yield f"data: {json.dumps({'type': 'init', 'status': job.status, 'total_pages': job.total_pages, 'processed_pages': job.processed_pages, 'current_page_name': job.current_page_name}, cls=UUIDEncoder)}\n\n"

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


def get_active_job_for_project(project_id: str, db: Session) -> Optional[ProcessingJob]:
    """Get the active (pending/processing) job for a project, if any."""
    return (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.project_id == project_id,
            ProcessingJob.status.in_(["pending", "processing"]),
        )
        .first()
    )


def pause_processing_job(project_id: str, db: Session) -> Optional[ProcessingJob]:
    """
    Pause an active processing job.

    The job will stop after completing the current page.
    Returns the job if paused, None if no active job found.
    """
    job = get_active_job_for_project(project_id, db)
    if job:
        job.status = "paused"
        db.commit()
        db.refresh(job)
        logger.info(f"Paused processing job {job.id} for project {project_id}")
    return job


def resume_processing_job(project_id: str, db: Session) -> Optional[ProcessingJob]:
    """
    Resume a paused processing job.

    Creates a new background task to continue processing from where it left off.
    Returns the job if resumed, None if no paused job found.
    """
    job = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.project_id == project_id,
            ProcessingJob.status == "paused",
        )
        .first()
    )
    if job:
        job.status = "processing"
        db.commit()
        db.refresh(job)
        logger.info(f"Resumed processing job {job.id} for project {project_id}")
    return job
