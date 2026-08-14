"""
Run this to process the latest matching emails in your Gmail inbox:

    python main.py

Output lands as one JSON file per email in ./output/
"""

import json
import os

from dotenv import load_dotenv
from imap_client import connect, search_messages, fetch_message
from email_utils import is_authorized_sender, get_body_and_images
from gemini_client import extract_statements

load_dotenv()

OUTPUT_DIR = "output"


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    approved_sender = os.environ.get("ALLOWED_SENDER_EMAIL", "").strip()
    if not approved_sender:
        raise EnvironmentError("ALLOWED_SENDER_EMAIL is not set in .env.")

    conn = connect()

    try:
        # Cheap server-side pre-filter; is_authorized_sender() does the exact,
        # case-insensitive check that actually matters.
        ids = search_messages(conn, from_domain=approved_sender, limit=10)

        if not ids:
            print(f"No emails found from '{approved_sender}'. Check that your test "
                  f"emails are in the Inbox (not archived/spam) and were actually "
                  f"sent from that exact address.")
            return

        for msg_id in ids:
            msg = fetch_message(conn, msg_id)
            subject = msg.get("Subject", "(no subject)")

            if not is_authorized_sender(msg):
                print(f"Skipped (unauthorized sender): {subject}")
                continue

            body_text, images = get_body_and_images(msg)

            if not images:
                print(f"Warning: no images found in '{subject}' — skipping Gemini call.")
                continue

            raw = extract_statements(
                sender=msg.get("From"),
                received_date=msg.get("Date"),
                body_text=body_text,
                images=images,
            )

            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                print(f"Model did not return valid JSON for '{subject}':\n{raw[:300]}")
                continue

            safe_id = msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
            out_path = os.path.join(OUTPUT_DIR, f"{safe_id}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)

            n_statements = len(result.get("statements", []))
            print(f"OK: '{subject}' -> {n_statements} statement(s) -> {out_path}")

    finally:
        conn.logout()


if __name__ == "__main__":
    main()
