import uuid
from supabase import create_client
from app.core.config import get_settings

settings = get_settings()

supabase = create_client(
    settings.supabase_url,
    settings.supabase_service_role_key,
)

BUCKET = settings.supabase_bucket


def upload_resume(file_name: str, file_bytes: bytes) -> str:
    """
    Upload resume to Supabase Storage.
    Returns the file path stored in the bucket.
    """

    unique_name = f"{uuid.uuid4()}_{file_name}"

    try:
        supabase.storage.from_(BUCKET).upload(
            path=unique_name,
            file=file_bytes,
            file_options={
                "content-type": "application/pdf",
                "upsert": "false",
            },
        )
        return unique_name

    except Exception as e:
        raise Exception(f"Supabase upload failed: {e}")


def download_resume(path: str) -> bytes:
    """
    Download resume bytes from Supabase Storage.
    """

    try:
        return supabase.storage.from_(BUCKET).download(path)
    except Exception as e:
        raise Exception(f"Failed to download resume: {e}")


def delete_resume(path: str):
    """
    Delete resume from Supabase Storage.
    """

    supabase.storage.from_(BUCKET).remove([path])


def file_exists(storage_path: str) -> bool:
    """
    Check if a resume exists in Supabase Storage.
    """
    try:
        # Using download-based validation as exists() might not be supported
        supabase.storage.from_(BUCKET).download(storage_path)
        return True
    except Exception as e:
        print(f"Error checking file existence: {e}")
        return False