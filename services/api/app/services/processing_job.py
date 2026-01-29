"""Backwards compatibility stub - module moved to core/processing_job.py"""
from app.services.core.processing_job import *  # noqa: F401, F403
from app.services.core.processing_job import (
    create_job_queue,
    emit_event,
    get_active_job_for_project,
    get_job_queue,
    pause_processing_job,
    process_project_pages,
    remove_job_queue,
    resume_processing_job,
    sse_event_generator,
    start_processing_job,
)
