"""Configuration management for the Transmission Apprentice Training App."""

import os
from pathlib import Path
from typing import Dict, Optional, Tuple

from dotenv import load_dotenv

# Load environment variables from .env file (resolve relative to project root)
_project_root = Path(__file__).resolve().parent.parent.parent
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


def _get_secret_from_file(file_path: str) -> Optional[str]:
    """Helper to read a secret value from a file, if the path is provided."""
    try:
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                return f.read().strip()
    except Exception:
        pass
    return None


def get_azure_config() -> Optional[Dict[str, str]]:
    """
    Get Azure OAuth configuration from environment variables.

    Returns:
        Dictionary with Azure configuration or None if not all required values are set.
    """
    tenant_id = (os.getenv("AZURE_TENANT_ID") or "").strip() or None
    client_id = (os.getenv("AZURE_CLIENT_ID") or "").strip() or None

    # Try environment variable first, then mounted GCP Secret Manager file.
    # Strip both so a blank/whitespace value can't bypass the file fallback.
    client_secret = (os.getenv("AZURE_CLIENT_SECRET") or "").strip() or None
    secret_file_path = (os.getenv("AZURE_CLIENT_SECRET_FILE") or "").strip()

    if not client_secret and secret_file_path:
        client_secret = _get_secret_from_file(secret_file_path)
        
    redirect_uri = (os.getenv("AZURE_REDIRECT_URI") or "").strip() or None
    object_id = (os.getenv("AZURE_OBJECT_ID") or "").strip() or None

    if not all([tenant_id, client_id, client_secret]):
        return None

    return {
        "tenant_id": tenant_id,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "object_id": object_id,
    }


def validate_azure_config() -> Tuple[bool, str]:
    """
    Validate that all required Azure configuration values are set.

    Returns:
        Tuple of (is_valid, message)
    """
    config = get_azure_config()

    if config is None:
        missing = []
        if not os.getenv("AZURE_TENANT_ID"):
            missing.append("AZURE_TENANT_ID")
        if not os.getenv("AZURE_CLIENT_ID"):
            missing.append("AZURE_CLIENT_ID")
        if not os.getenv("AZURE_CLIENT_SECRET"):
            missing.append("AZURE_CLIENT_SECRET")

        return False, f"Missing required configuration: {', '.join(missing)}"

    return True, "Configuration is valid"


def get_bigquery_config() -> Optional[Dict[str, str]]:
    """
    Get BigQuery configuration from environment variables.

    Returns:
        Dictionary with project and dataset, or None if not set.
    """
    project = os.getenv("GCP_PROJECT")
    dataset = os.getenv("BQ_DATASET")

    if not all([project, dataset]):
        return None

    return {
        "project": project,
        "dataset": dataset,
    }


def get_config() -> Dict[str, Optional[str]]:
    """
    Load the flat configuration dict consumed by pages (SharePoint, GCS, Azure ids).

    Returns:
        Dictionary of config values keyed by env var name.
    """
    return {
        # Azure / Entra ID
        "AZURE_TENANT_ID": os.getenv("AZURE_TENANT_ID"),
        "AZURE_CLIENT_ID": os.getenv("AZURE_CLIENT_ID"),
        "AZURE_OBJECT_ID": os.getenv("AZURE_OBJECT_ID"),
        # SharePoint — Set 2
        "SITE_2_ID": os.getenv("SITE_2_ID"),
        "DRIVE_2_ID": os.getenv("DRIVE_2_ID"),
        "Folder_2_path": os.getenv("Folder_2_path"),
        # GCS
        # "GCS_BUCKET": os.getenv("GCS_BUCKET", "training-evaluation-documents-dev"),
        "GCS_BUCKET": os.getenv("GCS_BUCKET"),
        # BigQuery
        "BIGQUERY_PROJECT": os.getenv("GCP_PROJECT"),
        "BIGQUERY_DATASET": os.getenv("BQ_DATASET"),
    }


def get_config_value(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get a single config value.

    Args:
        key: Config key name
        default: Default value if not found

    Returns:
        Config value or default
    """
    return get_config().get(key, default)
