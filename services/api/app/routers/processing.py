"""Processing endpoints for page and discipline analysis."""

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.discipline import Discipline
from app.models.page import Page
from app.models.project import Project

logger = logging.getLogger(__name__)

router = APIRouter(tags=["processing"])


# Response schemas
class ProcessUploadsResult(BaseModel):
    """Response for the upload processing pipeline."""

    total: int
    completed: int
    failed: int


@router.post(
    "/projects/{project_id}/process-uploads",
    response_model=ProcessUploadsResult,
)
async def process_uploads(
    project_id: str,
    db: Session = Depends(get_db),
) -> ProcessUploadsResult:
    """
    Mark all pages in a project as processed after upload.

    This is a placeholder endpoint - PDF processing has been removed.
    Pages are uploaded and ready for use immediately.
    """
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get all pages in project
    pages = (
        db.query(Page)
        .join(Discipline)
        .filter(Discipline.project_id == project_id)
        .all()
    )

    logger.info(f"Process uploads called for project {project_id}: {len(pages)} pages")

    return ProcessUploadsResult(
        total=len(pages),
        completed=len(pages),
        failed=0,
    )


@router.post("/projects/{project_id}/process-uploads-stream")
async def process_uploads_stream(
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    SSE endpoint for upload processing progress.

    This is a placeholder - PDF processing has been removed.
    Immediately returns complete status.
    """
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get page count
    total = (
        db.query(Page)
        .join(Discipline)
        .filter(Discipline.project_id == project_id)
        .count()
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        # Immediately complete - no processing needed
        progress = {
            "upload": total,
            "ocr": total,
            "ai": total,
            "png": total,
            "total": total,
            "complete": True,
        }
        yield f"data: {json.dumps(progress)}\n\n"

        logger.info(f"Stream processing complete for project {project_id}: {total} pages")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
