"""Isolated Microsoft Graph email test.
"""
import os
import sys
from pathlib import Path
from app.services.email_service import send_confirmation_email, _sender_mailbox

# Make `app` importable and load .env.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Force REAL sending for this script only (does not affect the app).
# Both flags are required: EMAIL_DRY_RUN defaults to true and would otherwise
# intercept the send as a simulation.
os.environ["EMAIL_ENABLED"] = "true"
os.environ["EMAIL_DRY_RUN"] = "false"




def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/send_test_email.py <recipient_email>")
        return 2

    recipient = sys.argv[1]
    sender = _sender_mailbox()
    if not sender:
        print("❌ GRAPH_SENDER_MAILBOX is not set in .env — set it first.")
        return 1

    print(f"Sending test email from {sender} to {recipient} ...")
    status, err = send_confirmation_email(
        recipient_email=recipient,
        subject="Graph email test — Apprentice Training App",
        body="If you received this, app-only Mail.Send is working correctly.",
    )
    if status == "SENT":
        print("✅ SUCCESS — Graph accepted the message (HTTP 202). Check the inbox.")
        return 0

    print(f"❌ {status} — {err}")
    print("   401/invalid_client  → client secret wrong/expired")
    print("   403/Authorization_RequestDenied → Mail.Send app permission/consent missing")
    print("   ErrorAccessDenied on sendMail   → ApplicationAccessPolicy / sender mailbox")
    print("   ErrorInvalidRecipients          → recipient address")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
