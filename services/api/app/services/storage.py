"""
Supabase Storage service for file uploads.

TODO: Implement in storage integration phase.
"""


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
    raise NotImplementedError("Storage integration not yet implemented")


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
    raise NotImplementedError("Storage integration not yet implemented")


async def get_download_url(storage_path: str, expires_in: int = 3600) -> str:
    """
    Get a signed download URL for a file.

    Args:
        storage_path: Path in Supabase Storage
        expires_in: URL expiration time in seconds (default 1 hour)

    Returns:
        Signed download URL
    """
    raise NotImplementedError("Storage integration not yet implemented")


async def delete_file(storage_path: str) -> None:
    """
    Delete a file from Supabase Storage.

    Args:
        storage_path: Path to delete
    """
    raise NotImplementedError("Storage integration not yet implemented")
