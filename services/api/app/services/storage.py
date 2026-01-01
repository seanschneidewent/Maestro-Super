"""
Supabase Storage service for file operations.
"""

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


async def download_file(storage_path: str) -> bytes:
    """
    Download a file from Supabase Storage.

    Args:
        storage_path: Path in Supabase Storage (e.g., "projects/abc-123/file.pdf")

    Returns:
        File bytes
    """
    try:
        supabase = _get_supabase_client()
        response = supabase.storage.from_(BUCKET_NAME).download(storage_path)
        return response
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
