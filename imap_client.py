"""
Reads Gmail over plain IMAP using an App Password.

This deliberately avoids Google Cloud Console / the Gmail API entirely —
no project, no OAuth client, no billing account link. App Passwords are a
native Gmail security feature (require 2-Step Verification), not a workaround.
"""

import imaplib
import email
import os
from dotenv import load_dotenv

load_dotenv()

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


def connect():
    address = os.environ.get("GMAIL_ADDRESS")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not address or not app_password:
        raise EnvironmentError(
            "GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in .env. "
            "See README.md for how to generate an App Password."
        )
    conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    conn.login(address, app_password)
    return conn


def search_messages(conn, from_domain, mailbox="INBOX", limit=10):
    """
    Returns the most recent `limit` message IDs from senders whose address
    contains from_domain. This is a cheap server-side pre-filter — the real
    sender-domain check still happens in email_utils.is_authorized_sender,
    since IMAP's FROM search is a loose substring match.
    """
    conn.select(mailbox)
    status, data = conn.search(None, f'(FROM "{from_domain}")')
    if status != "OK":
        return []
    ids = data[0].split()
    return ids[-limit:]


def fetch_message(conn, msg_id):
    status, data = conn.fetch(msg_id, "(RFC822)")
    if status != "OK" or not data or data[0] is None:
        raise RuntimeError(f"Could not fetch message {msg_id}")
    raw_email = data[0][1]
    return email.message_from_bytes(raw_email)
