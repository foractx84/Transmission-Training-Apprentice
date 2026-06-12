"""Role-based access control — page and feature permission checks."""

from app.core.auth import AzureAuth

# Azure AD App Role values (must match the 'Value' field in App Registration)
ROLE_ADMIN      = "training-admin"
ROLE_AUDITOR    = "training-auditor"
ROLE_APPRENTICE = "training-apprentice"
ROLE_SUPERVISOR = "training-supervisor"


def has_role(auth: AzureAuth, role: str) -> bool:
    """Return True if the authenticated user has the given app role."""
    roles = auth.get_user_roles() or []
    return role in roles
