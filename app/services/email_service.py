"""Email service for application notifications.

For now this is a placeholder. Later we can replace this with
Microsoft Graph Mail.Send or another approved company email method.
"""
import logging

logger = logging.getLogger(__name__)


def send_confirmation_email(
    recipient_email: str | None,
    subject: str,
    body: str,
) -> tuple[bool, str | None]:
    """Send confirmation email.

    Returns:
        (True, None) if successful
        (False, error_message) if failed
    """

    if not recipient_email:
        return False, "Missing recipient email"

    logger.info("[EMAIL placeholder] suppressed send (not yet wired to a mail provider)")
    logger.debug(
        "[EMAIL placeholder] would send to %s | subject=%s | body=%s",
        recipient_email,
        subject,
        body,
    )

    return True, None
