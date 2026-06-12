"""SharePoint service — interact with Microsoft Graph API for file operations."""
from typing import List, Dict, Optional
from urllib.parse import quote
import requests

_LIST_TIMEOUT = 30
_DOWNLOAD_TIMEOUT = 60

def _get_graph_headers(auth_token: str) -> Dict[str, str]:
    """Return headers for Microsoft Graph API calls."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }

def list_sharepoint_folder_items(
    auth_token: str,
    site_id: str,
    drive_id: str,
    folder_path: str,
) -> List[Dict]:
    """
    List all files in a SharePoint folder via Microsoft Graph.
    
    Args:
        auth_token: OAuth token from Entra ID
        site_id: Full site ID (NOT USED — kept for backwards compatibility)
        drive_id: Drive ID (e.g. "b!_SGSpf8u...")
        folder_path: Path like "ProficiencyPlus/CEHE/Transmission"
    
    Returns:
        List of file dicts: [{"name": "...", "id": "...", "size": ...}, ...]
    """
    headers = _get_graph_headers(auth_token)
    
    # Use drive-based endpoint (works reliably)
    # Format: /drives/{drive-id}/root:/{folder-path}:/children
    encoded_path = quote(folder_path, safe="/")
    url: str | None = (
        f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{encoded_path}:/children"
    )

    items: List[Dict] = []
    # Follow @odata.nextLink so folders with more than one page are fully read.
    while url:
        try:
            response = requests.get(url, headers=headers, timeout=_LIST_TIMEOUT)
            response.raise_for_status()
        except requests.exceptions.Timeout as e:
            raise Exception(f"Graph API timed out after {_LIST_TIMEOUT}s listing {folder_path}") from e
        except requests.exceptions.HTTPError as e:
            raise Exception(f"Graph API error: {response.status_code} - {response.text}") from e

        data = response.json()
        items.extend(data.get("value", []))
        url = data.get("@odata.nextLink")

    # Filter only files (not folders)
    files = [
        {
            "name": item["name"],
            "id": item["id"],
            "size": item.get("size", 0),
            "webUrl": item.get("webUrl", ""),
        }
        for item in items
        if "file" in item  # Has file extension
    ]

    return files

def download_file_from_sharepoint(
    auth_token: str,
    site_id: str,
    drive_id: str,
    file_id: str,
) -> bytes:
    """
    Download file content from SharePoint.
    
    Args:
        auth_token: OAuth token
        site_id: Full site ID (NOT USED — kept for backwards compatibility)
        drive_id: Drive ID
        file_id: File item ID
    
    Returns:
        File bytes
    """
    headers = _get_graph_headers(auth_token)
    
    # Use drive-based endpoint
    # Format: /drives/{drive-id}/items/{file-id}/content
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/content"

    try:
        response = requests.get(url, headers=headers, stream=True, timeout=_DOWNLOAD_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.Timeout as e:
        raise Exception(f"Graph API timed out after {_DOWNLOAD_TIMEOUT}s downloading file {file_id}") from e
    except requests.exceptions.HTTPError as e:
        raise Exception(f"Graph API error: {response.status_code} - {response.text}") from e
    
    return response.content