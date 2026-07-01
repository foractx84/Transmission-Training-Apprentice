"""Email service — Microsoft Graph (application permission) sendMail.
"""
from __future__ import annotations

import os
import logging

import msal
import requests

from app.core.config import get_azure_config

logger = logging.getLogger(__name__)

# Status constants — also the exact strings written to communication_log.status.
SENT = "SENT"
FAILED = "FAILED"
SKIPPED = "SKIPPED"
DRY_RUN = "DRY_RUN"

_GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]
_GRAPH_SENDMAIL_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"

_TRUTHY = ("1", "true", "yes", "on")


def _email_enabled() -> bool:
    return os.getenv("EMAIL_ENABLED", "false").strip().lower() in _TRUTHY


def _dry_run() -> bool:
    # Default true: fail safe — an unset flag must never send real email.
    return os.getenv("EMAIL_DRY_RUN", "true").strip().lower() in _TRUTHY


def _sender_mailbox() -> str | None:
    return (os.getenv("GRAPH_SENDER_MAILBOX") or "").strip() or None


def _acquire_app_token() -> tuple[str | None, str | None]:
    """App-only Graph token via client credentials. Returns (token, error)."""
    cfg = get_azure_config()
    if not cfg:
        return None, "Azure config missing (AZURE_TENANT_ID/CLIENT_ID/CLIENT_SECRET)."

    app = msal.ConfidentialClientApplication(
        client_id=cfg["client_id"],
        client_credential=cfg["client_secret"],
        authority=f"https://login.microsoftonline.com/{cfg['tenant_id']}",
    )
    result = app.acquire_token_for_client(scopes=_GRAPH_SCOPE)
    token = result.get("access_token")
    if not token:
        return None, result.get("error_description") or result.get("error") or "Token acquisition failed."
    return token, None


def send_confirmation_email(
    recipient_email: str | None,
    subject: str,
    body: str,
) -> tuple[str, str | None]:
    """Send a confirmation email.

    Returns:
        (status, error) where status is SENT / FAILED / SKIPPED / DRY_RUN.
        error is None on SENT and DRY_RUN; a reason string otherwise.
    """
    # ── No recipient: can't send or even simulate ───────────────────────────
    if not recipient_email:
        return SKIPPED, "Missing recipient email"

    # ── Dry run: master safety switch — log only, never touch the network ────
    if _dry_run():
        logger.info(
            "[EMAIL DRY_RUN] would send to %s | subject=%s", recipient_email, subject
        )
        logger.debug("[EMAIL DRY_RUN] body_len=%d", len(body))
        return DRY_RUN, None

    # ── Email off (and not dry-run): intentionally suppress, send nothing ────
    if not _email_enabled():
        logger.info("[EMAIL SKIPPED] EMAIL_ENABLED is off — suppressed send to %s", recipient_email)
        return SKIPPED, "Email disabled (EMAIL_ENABLED is off)"

    # ── Enabled: real Microsoft Graph sendMail (app-only) ───────────────────
    sender = _sender_mailbox()
    if not sender:
        return FAILED, "GRAPH_SENDER_MAILBOX is not set"

    token, err = _acquire_app_token()
    if not token:
        logger.error("Email auth failed: %s", err)
        return FAILED, f"Auth error: {err}"

    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": recipient_email}}],
        },
        "saveToSentItems": True,
    }

    try:
        resp = requests.post(
            _GRAPH_SENDMAIL_URL.format(sender=sender),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
    except Exception as e:
        logger.error("Email send network error: %s", e)
        return FAILED, f"Network error: {e}"

    # Graph sendMail returns 202 Accepted on success.
    if resp.status_code == 202:
        return SENT, None

    logger.error("Email send failed (HTTP %s): %s", resp.status_code, resp.text)
    return FAILED, f"Graph {resp.status_code}: {resp.text[:300]}"
