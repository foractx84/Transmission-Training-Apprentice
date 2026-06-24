"""Google Cloud Storage service — upload/download files.

Low-level Google client errors (permission denied, missing bucket/object,
network failures, missing credentials) are translated into a single, friendly
``GCSError`` so the calling page can show a clear message to the user instead of
leaking a raw stack trace. This mirrors the SharePoint service, which also
raises descriptive exceptions for its callers to handle.
"""
import logging
from typing import List

from google.cloud import storage
from google.api_core.exceptions import Forbidden, NotFound, GoogleAPIError
from google.auth.exceptions import GoogleAuthError

logger = logging.getLogger(__name__)


class GCSError(Exception):
    """A storage operation failed. The message is safe to show to users."""


def get_gcs_client() -> storage.Client:
    """Return a GCS client using Application Default Credentials."""
    try:
        return storage.Client()
    except GoogleAuthError as e:
        logger.error("GCS authentication error: %s", e)
        raise GCSError(
            "Could not connect to file storage — authentication failed. "
            "Please contact your administrator."
        ) from e


def upload_file_to_gcs(
    bucket_name: str,
    file_bytes: bytes,
    filename: str,
    folder_prefix: str = "jpm-hosd-forms",
) -> str:
    """
    Upload file bytes to GCS bucket.

    Args:
        bucket_name: GCS bucket name
        file_bytes: File content as bytes
        filename: Filename to store as
        folder_prefix: Folder path in bucket

    Returns:
        gs://bucket/path/filename

    Raises:
        GCSError: with a user-friendly message if the upload fails.
    """
    blob_path = f"{folder_prefix}/{filename}"
    try:
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(file_bytes, content_type="application/pdf")
    except Forbidden as e:
        logger.error("GCS permission denied uploading %s: %s", blob_path, e)
        raise GCSError(
            f"Permission denied uploading “{filename}” to storage. "
            "Please contact your administrator."
        ) from e
    except NotFound as e:
        logger.error("GCS bucket not found (%s): %s", bucket_name, e)
        raise GCSError(
            "The storage bucket could not be found. Please contact your administrator."
        ) from e
    except GoogleAPIError as e:
        logger.error("GCS error uploading %s: %s", blob_path, e)
        raise GCSError(
            f"Couldn't upload “{filename}” to storage. Please try again later."
        ) from e

    return f"gs://{bucket_name}/{blob_path}"


def list_files_in_gcs_folder(
    bucket_name: str,
    folder_prefix: str = "jpm-hosd-forms",
) -> List[str]:
    """
    List all filenames in a GCS folder.

    Returns:
        List of filenames (without folder prefix)

    Raises:
        GCSError: with a user-friendly message if the listing fails.
    """
    try:
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=f"{folder_prefix}/")

        filenames = []
        for blob in blobs:
            # Remove folder prefix
            filename = blob.name.replace(f"{folder_prefix}/", "")
            if filename:  # Exclude empty names
                filenames.append(filename)
    except Forbidden as e:
        logger.error("GCS permission denied listing %s: %s", bucket_name, e)
        raise GCSError(
            "Permission denied reading the form list from storage. "
            "Please contact your administrator."
        ) from e
    except NotFound as e:
        logger.error("GCS bucket not found (%s): %s", bucket_name, e)
        raise GCSError(
            "The storage bucket could not be found. Please contact your administrator."
        ) from e
    except GoogleAPIError as e:
        logger.error("GCS error listing %s: %s", bucket_name, e)
        raise GCSError(
            "Couldn't load the list of forms from storage. Please try again later."
        ) from e

    return sorted(filenames)


def download_file_from_gcs(
    bucket_name: str,
    filename: str,
    folder_prefix: str = "jpm-hosd-forms",
) -> bytes:
    """
    Download file bytes from GCS.

    Returns:
        File content as bytes

    Raises:
        GCSError: with a user-friendly message if the download fails.
    """
    blob_path = f"{folder_prefix}/{filename}"
    try:
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        return blob.download_as_bytes()
    except Forbidden as e:
        logger.error("GCS permission denied downloading %s: %s", blob_path, e)
        raise GCSError(
            f"Permission denied downloading “{filename}” from storage. "
            "Please contact your administrator."
        ) from e
    except NotFound as e:
        logger.error("GCS file not found (%s): %s", blob_path, e)
        raise GCSError(
            f"“{filename}” could not be found in storage. "
            "It may have been moved or removed — try syncing again."
        ) from e
    except GoogleAPIError as e:
        logger.error("GCS error downloading %s: %s", blob_path, e)
        raise GCSError(
            f"Couldn't download “{filename}” from storage. Please try again later."
        ) from e


def check_file_exists_in_gcs(
    bucket_name: str,
    filename: str,
    folder_prefix: str = "jpm-hosd-forms",
) -> bool:
    """Check if file exists in GCS.

    Raises:
        GCSError: with a user-friendly message if the check fails.
    """
    blob_path = f"{folder_prefix}/{filename}"
    try:
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        return blob.exists()
    except GoogleAPIError as e:
        logger.error("GCS error checking %s: %s", blob_path, e)
        raise GCSError(
            "Couldn't check storage right now. Please try again later."
        ) from e
