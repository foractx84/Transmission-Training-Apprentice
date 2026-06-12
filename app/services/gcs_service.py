"""Google Cloud Storage service — upload/download files."""
from typing import List, Optional
from google.cloud import storage
from io import BytesIO

def get_gcs_client() -> storage.Client:
    """Return a GCS client using Application Default Credentials."""
    return storage.Client()

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
    """
    client = get_gcs_client()
    bucket = client.bucket(bucket_name)
    blob_path = f"{folder_prefix}/{filename}"
    blob = bucket.blob(blob_path)
    
    blob.upload_from_string(file_bytes)
    
    return f"gs://{bucket_name}/{blob_path}"

def list_files_in_gcs_folder(
    bucket_name: str,
    folder_prefix: str = "jpm-hosd-forms",
) -> List[str]:
    """
    List all filenames in a GCS folder.
    
    Returns:
        List of filenames (without folder prefix)
    """
    client = get_gcs_client()
    bucket = client.bucket(bucket_name)
    
    blobs = bucket.list_blobs(prefix=f"{folder_prefix}/")
    
    filenames = []
    for blob in blobs:
        # Remove folder prefix
        filename = blob.name.replace(f"{folder_prefix}/", "")
        if filename:  # Exclude empty names
            filenames.append(filename)
    
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
    """
    client = get_gcs_client()
    bucket = client.bucket(bucket_name)
    blob_path = f"{folder_prefix}/{filename}"
    blob = bucket.blob(blob_path)
    
    return blob.download_as_bytes()

def check_file_exists_in_gcs(
    bucket_name: str,
    filename: str,
    folder_prefix: str = "jpm-hosd-forms",
) -> bool:
    """Check if file exists in GCS."""
    client = get_gcs_client()
    bucket = client.bucket(bucket_name)
    blob_path = f"{folder_prefix}/{filename}"
    blob = bucket.blob(blob_path)
    
    return blob.exists()