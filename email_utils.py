"""
Parses a Python stdlib email.message.Message (as returned by imap_client.fetch_message):
checks the sender against an approved address, and pulls out plain-text body +
image attachments/inline images.
"""

import os
from email.utils import parseaddr
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()


def is_authorized_sender(msg):
    """
    Checks the email's From address against ALLOWED_SENDER_EMAIL in .env
    (exact match, case-insensitive). Set that once and every file in this
    project reads it from here — no other file needs editing.
    """
    approved = os.environ.get("ALLOWED_SENDER_EMAIL", "").strip().lower()
    if not approved:
        raise EnvironmentError(
            "ALLOWED_SENDER_EMAIL is not set in .env. Add the exact Gmail "
            "address you want to accept emails from."
        )
    _, addr = parseaddr(msg.get("From", ""))
    return addr.strip().lower() == approved


def get_body_and_images(msg):
    """
    Returns (body_text: str, images: list[dict]) where each image dict is
    {"filename", "mime_type", "bytes"}.
    """
    body_chunks = []
    images = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            filename = part.get_filename()

            # Text body part (skip if it's actually an attachment)
            if content_type in ("text/plain", "text/html") and "attachment" not in content_disposition:
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if payload:
                    body_chunks.append((content_type, payload.decode(charset, errors="replace")))

            # Image attachment or inline image
            elif filename and content_type.startswith("image/"):
                payload = part.get_payload(decode=True)
                if payload:
                    images.append({
                        "filename": filename,
                        "mime_type": content_type,
                        "bytes": payload,
                    })
    else:
        content_type = msg.get_content_type()
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        if payload:
            body_chunks.append((content_type, payload.decode(charset, errors="replace")))

    text = next((c for t, c in body_chunks if t == "text/plain"), None)
    if text is None:
        html = next((c for t, c in body_chunks if t == "text/html"), "")
        text = BeautifulSoup(html, "html.parser").get_text("\n")

    return text, images
