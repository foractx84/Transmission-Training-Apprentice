"""Isolated Microsoft Graph email test.

Use this for the "send one test email to yourself" step BEFORE turning email on
app-wide and BEFORE submitting any real JPM/HOSD form.

It forces real sending in THIS process only (EMAIL_ENABLED=true here), so the
running app stays in safe stub mode. Requires GRAPH_SENDER_MAILBOX in .env and
Mail.Send (Application) consent already granted.

Usage:
    python scripts/send_test_email.py you@centerpointenergy.com
"""
import os
import sys
from pathlib import Path

# Make `app` importable and load .env.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Force REAL sending for this script only (does not affect the app).
os.environ["EMAIL_ENABLED"] = "true"

from app.services.email_service import send_confirmation_email, _sender_mailbox


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
    ok, err = send_confirmation_email(
        recipient_email=recipient,
        subject="Graph email test — Apprentice Training App",
        body="If you received this, app-only Mail.Send is working correctly.",
    )
    if ok:
        print("✅ SUCCESS — Graph accepted the message (HTTP 202). Check the inbox.")
        return 0

    print(f"❌ FAILED — {err}")
    print("   401/invalid_client  → client secret wrong/expired")
    print("   403/Authorization_RequestDenied → Mail.Send app permission/consent missing")
    print("   ErrorAccessDenied on sendMail   → ApplicationAccessPolicy / sender mailbox")
    print("   ErrorInvalidRecipients          → recipient address")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
