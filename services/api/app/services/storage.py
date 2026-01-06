"""
Supabase Storage service for file operations.
"""

import asyncio
import logging

from supabase import create_client

from app.config import get_settings

logger = logging.getLogger(__name__)

# Storage bucket name (matches frontend)
BUCKET_NAME = "project-files"


def _get_supabase_client():
    """Get Supabase client with service key for backend operations."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_key:
        raise ValueError("Supabase URL and service key must be configured")
    return create_client(settings.supabase_url, settings.supabase_service_key)


async def download_file(storage_path: str, timeout: float = 60.0) -> bytes:
    """
    Download a file from Supabase Storage with timeout.

    Args:
        storage_path: Path in Supabase Storage (e.g., "projects/abc-123/file.pdf")
        timeout: Download timeout in seconds (default 60s for large PDFs)

    Returns:
        File bytes

    Raises:
        TimeoutError: If download takes longer than timeout
    """
    try:
        supabase = _get_supabase_client()
        # Run blocking Supabase call in thread pool with timeout
        response = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: supabase.storage.from_(BUCKET_NAME).download(storage_path)
            ),
            timeout=timeout,
        )
        return response
    except asyncio.TimeoutError:
        logger.error(f"Download timed out after {timeout}s: {storage_path}")
        raise TimeoutError(f"Download timed out after {timeout}s: {storage_path}")
    except Exception as e:
        logger.error(f"Failed to download file {storage_path}: {e}")
        raise


async def upload_pdf(
    file_content: bytes,
    filename: str,
    user_id: str,
    project_id: str,
) -> str:
    """
    Upload a PDF file to Supabase Storage.

    Args:
        file_content: PDF file bytes
        filename: Original filename
        user_id: Owner user ID
        project_id: Parent project ID

    Returns:
        Storage path for the uploaded file
    """
    storage_path = f"projects/{project_id}/{filename}"
    try:
        supabase = _get_supabase_client()
        supabase.storage.from_(BUCKET_NAME).upload(
            storage_path,
            file_content,
            {"content-type": "application/pdf", "cache-control": "3600"},
        )
        return storage_path
    except Exception as e:
        logger.error(f"Failed to upload PDF {filename}: {e}")
        raise


async def upload_snapshot(
    image_content: bytes,
    pointer_id: str,
    user_id: str,
) -> str:
    """
    Upload a context pointer snapshot to Supabase Storage.

    Args:
        image_content: PNG image bytes
        pointer_id: Context pointer ID
        user_id: Owner user ID

    Returns:
        Storage path for the uploaded snapshot
    """
    storage_path = f"snapshots/{user_id}/{pointer_id}.png"
    try:
        supabase = _get_supabase_client()
        supabase.storage.from_(BUCKET_NAME).upload(
            storage_path,
            image_content,
            {"content-type": "image/png", "cache-control": "3600"},
        )
        return storage_path
    except Exception as e:
        logger.error(f"Failed to upload snapshot for pointer {pointer_id}: {e}")
        raise


async def get_download_url(storage_path: str, expires_in: int = 3600) -> str:
    """
    Get a signed download URL for a file.

    Args:
        storage_path: Path in Supabase Storage
        expires_in: URL expiration time in seconds (default 1 hour)

    Returns:
        Signed download URL
    """
    try:
        supabase = _get_supabase_client()
        response = supabase.storage.from_(BUCKET_NAME).create_signed_url(
            storage_path, expires_in
        )
        return response["signedURL"]
    except Exception as e:
        logger.error(f"Failed to get signed URL for {storage_path}: {e}")
        raise


async def delete_file(storage_path: str) -> None:
    """
    Delete a file from Supabase Storage.

    Args:
        storage_path: Path to delete
    """
    try:
        supabase = _get_supabase_client()
        supabase.storage.from_(BUCKET_NAME).remove([storage_path])
    except Exception as e:
        logger.error(f"Failed to delete file {storage_path}: {e}")
        raise


async def upload_page_image(
    image_content: bytes,
    project_id: str,
    page_id: str,
) -> str:
    """
    Upload a pre-rendered page image (PNG) to Supabase Storage.

    Args:
        image_content: PNG image bytes
        project_id: Project ID
        page_id: Page ID

    Returns:
        Storage path for the uploaded image
    """
    storage_path = f"page-images/{project_id}/{page_id}.png"
    try:
        supabase = _get_supabase_client()
        supabase.storage.from_(BUCKET_NAME).upload(
            storage_path,
            image_content,
            {"content-type": "image/png", "cache-control": "86400"},  # 24hr cache
        )
        logger.info(f"Uploaded page image: {storage_path}")
        return storage_path
    except Exception as e:
        logger.error(f"Failed to upload page image for page {page_id}: {e}")
        raise


async def get_public_url(storage_path: str) -> str:
    """
    Get the public URL for a file in storage.

    Args:
        storage_path: Path in Supabase Storage

    Returns:
        Public URL for the file
    """
    try:
        supabase = _get_supabase_client()
        response = supabase.storage.from_(BUCKET_NAME).get_public_url(storage_path)
        return response
    except Exception as e:
        logger.error(f"Failed to get public URL for {storage_path}: {e}")
        raise
