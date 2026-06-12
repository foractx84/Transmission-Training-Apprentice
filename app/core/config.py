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


def get_azure_config() -> Optional[Dict[str, str]]:
    """
    Get Azure OAuth configuration from environment variables.

    Returns:
        Dictionary with Azure configuration or None if not all required values are set.
    """
    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    redirect_uri = os.getenv("AZURE_REDIRECT_URI", "http://localhost:8501")
    object_id = os.getenv("AZURE_OBJECT_ID")  # Optional, for reference

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
        "AZURE_CLIENT_SECRET": os.getenv("AZURE_CLIENT_SECRET"),
        "AZURE_OBJECT_ID": os.getenv("AZURE_OBJECT_ID"),

        # SharePoint — Set 2
        "SITE_2_ID": os.getenv("SITE_2_ID"),
        "DRIVE_2_ID": os.getenv("DRIVE_2_ID"),
        "Folder_2_path": os.getenv("Folder_2_path"),

        # GCS
        "GCS_BUCKET": os.getenv("GCS_BUCKET", "training-evaluation-documents-dev"),

        # BigQuery
        "BIGQUERY_PROJECT": os.getenv("BIGQUERY_PROJECT"),
        "BIGQUERY_DATASET": os.getenv("BIGQUERY_DATASET", "apprentice_training"),
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
