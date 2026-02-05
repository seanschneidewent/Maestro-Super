"""
Pass 2 background worker.

Polls for Pointers with enrichment_status='pending', enriches them with
Gemini vision analysis, generates embeddings, and writes results back.

Runs as an asyncio background task for the lifetime of the server.
"""

import asyncio
import logging
import time

from sqlalchemy.orm import Session as DBSession, joinedload

from app.config import get_settings
from app.database.session import SessionLocal
from app.models.pointer import Pointer
from app.models.page import Page
from app.models.discipline import Discipline
from app.services.core.pass2_enrichment import EnrichmentInput, enrich_pointer
from app.services.providers.voyage import embed_text
from app.services.utils.storage import download_file
from app.utils.retry import with_retry

logger = logging.getLogger(__name__)


async def _reset_stale_processing(db: DBSession) -> int:
    """
    Reset any pointers stuck in 'processing' back to 'pending'.

    This handles the case where the server restarted mid-enrichment.
    Returns the number of pointers reset.
    """
    stale = (
        db.query(Pointer)
        .filter(Pointer.enrichment_status == "processing")
        .all()
    )
    for ptr in stale:
        ptr.enrichment_status = "pending"
    if stale:
        db.commit()
        logger.info("Reset %d stale 'processing' pointers to 'pending'", len(stale))
    return len(stale)


async def _fetch_pending_batch(db: DBSession, batch_size: int) -> list[Pointer]:
    """Fetch a batch of pending pointers ordered by creation time."""
    return (
        db.query(Pointer)
        .filter(Pointer.enrichment_status == "pending")
        .filter(Pointer.png_path.isnot(None))  # Must have a cropped image
        .order_by(Pointer.created_at)
        .limit(batch_size)
        .all()
    )


async def _enrich_single_pointer(pointer_id: str) -> None:
    """
    Enrich a single Pointer end-to-end.

    Uses its own DB session to avoid cross-task conflicts.
    1. Mark as 'processing'
    2. Load context (page, discipline)
    3. Download cropped image
    4. Call Gemini enrichment
    5. Generate embedding
    6. Write results back
    7. Mark as 'complete' (or 'failed' on error)
    """
    db = SessionLocal()
    try:
        # Load pointer with relationships
        pointer = (
            db.query(Pointer)
            .options(
                joinedload(Pointer.page).joinedload(Page.discipline)
            )
            .filter(Pointer.id == pointer_id)
            .first()
        )
        if not pointer:
            logger.warning("Pointer %s not found, skipping", pointer_id)
            return

        if pointer.enrichment_status != "pending":
            logger.info("Pointer %s no longer pending (status=%s), skipping", pointer_id, pointer.enrichment_status)
            return

        # Mark as processing
        pointer.enrichment_status = "processing"
        db.commit()

        page = pointer.page
        discipline = page.discipline if page else None

        if not page or not pointer.png_path:
            logger.warning("Pointer %s missing page or png_path, marking failed", pointer_id)
            pointer.enrichment_status = "failed"
            pointer.enrichment_metadata = {"error": "Missing page or png_path"}
            db.commit()
            return

        # Download cropped image from Supabase storage
        try:
            cropped_image = await download_file(pointer.png_path)
        except Exception as e:
            logger.error("Failed to download crop for pointer %s: %s", pointer_id, e)
            pointer.enrichment_status = "failed"
            pointer.enrichment_metadata = {"error": f"Download failed: {e}"}
            db.commit()
            return

        # Build enrichment input
        enrichment_input = EnrichmentInput(
            pointer_id=pointer_id,
            cropped_image_bytes=cropped_image,
            sheet_reflection=page.sheet_reflection or "",
            page_name=page.page_name or "Unknown",
            discipline_name=discipline.display_name if discipline else "Unknown",
            pointer_title=pointer.title or "Untitled",
        )

        # Call Gemini enrichment with retry
        enrichment_output = await with_retry(
            enrich_pointer,
            enrichment_input,
            max_attempts=2,
            base_delay=2.0,
            max_delay=10.0,
        )

        # Generate embedding from the rich description
        embedding = await with_retry(
            embed_text,
            enrichment_output.embedding_text,
            max_attempts=2,
            base_delay=1.0,
            max_delay=5.0,
        )

        # Write results back to pointer
        pointer.description = enrichment_output.rich_description
        pointer.cross_references = enrichment_output.cross_references
        pointer.embedding = embedding
        pointer.enrichment_status = "complete"
        pointer.enrichment_metadata = {
            "enriched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cross_ref_count": len(enrichment_output.cross_references),
            "description_length": len(enrichment_output.rich_description),
        }
        db.commit()

        logger.info(
            "Pointer %s enriched successfully — %d chars, %d cross-refs",
            pointer_id,
            len(enrichment_output.rich_description),
            len(enrichment_output.cross_references),
        )

    except Exception as e:
        logger.error("Enrichment failed for pointer %s: %s", pointer_id, e, exc_info=True)
        try:
            # Re-fetch in case session is dirty
            pointer = db.query(Pointer).filter(Pointer.id == pointer_id).first()
            if pointer:
                pointer.enrichment_status = "failed"
                pointer.enrichment_metadata = {"error": str(e)[:500]}
                db.commit()
        except Exception:
            logger.error("Failed to mark pointer %s as failed", pointer_id)
    finally:
        db.close()


async def run_pass2_worker() -> None:
    """
    Background worker that polls for pending Pointers and enriches them.

    Lifecycle:
    1. On startup, reset any 'processing' status back to 'pending'
    2. Poll loop: query pending pointers, process batch with concurrency limit
    3. Sleep between poll cycles

    Runs for the lifetime of the server process.
    """
    settings = get_settings()
    max_concurrent = settings.pass2_max_concurrent
    poll_interval = settings.pass2_poll_interval

    logger.info(
        "Pass 2 worker starting — max_concurrent=%d, poll_interval=%.1fs",
        max_concurrent,
        poll_interval,
    )

    # Reset stale pointers from previous server lifecycle
    db = SessionLocal()
    try:
        await _reset_stale_processing(db)
    finally:
        db.close()

    semaphore = asyncio.Semaphore(max_concurrent)

    async def _bounded_enrich(pointer_id: str) -> None:
        async with semaphore:
            await _enrich_single_pointer(pointer_id)

    while True:
        try:
            db = SessionLocal()
            try:
                batch = await _fetch_pending_batch(db, batch_size=max_concurrent * 2)
            finally:
                db.close()

            if not batch:
                await asyncio.sleep(poll_interval)
                continue

            logger.info("Pass 2 worker found %d pending pointers", len(batch))

            # Process batch concurrently with semaphore limit
            pointer_ids = [p.id for p in batch]
            tasks = [_bounded_enrich(pid) for pid in pointer_ids]
            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            logger.error("Pass 2 worker error: %s", e, exc_info=True)
            await asyncio.sleep(poll_interval * 2)  # Back off on errors
