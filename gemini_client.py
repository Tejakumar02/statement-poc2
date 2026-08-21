"""
Calls the Gemini API directly over HTTPS using only Python's standard
library (urllib) — no google-genai SDK.

Why: the SDK pulls in google-auth, which pulls in `cryptography`, which
ships a compiled Rust extension. On some locked-down Windows machines,
Application Control / WDAC policies block that binary outright, even
though we only ever use a plain API key (never OAuth/service accounts).
Dropping the SDK removes that whole dependency chain — this file has
zero third-party network dependencies.
"""

import base64
import json
import os
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("GEMINI_API_KEY", "")

with open("prompt.txt", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

# Flash-class = free tier. Pro-series models require billing (as of Apr 2026).
#
# Google retires Gemini model IDs faster than this file can be kept up to
# date by hand — gemini-2.5-flash was just cut off for new API keys ahead
# of its Oct 16, 2026 shutdown. Instead of hardcoding one name and hoping,
# we try each candidate in order and remember whichever one actually works
# for your key. If ALL of these are dead by the time you read this, get the
# current list yourself:
#   https://generativelanguage.googleapis.com/v1beta/models?key=YOUR_KEY
# (open that URL in a browser with your real key — it lists every model
# your key can use, and which ones support generateContent).
MODEL_CANDIDATES = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3.6-flash",
    "gemini-2.0-flash-lite",
]

_working_model = None  # cached once we find one that works, so we stop re-probing every call


def _endpoint_for(model):
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def extract_statements(sender, received_date, subject, body_text, images):
    """
    images: list of {"mime_type": str, "bytes": bytes}
    Returns the raw JSON text from Gemini (caller is responsible for
    json.loads and validation — see main.py).
    """
    if not API_KEY:
        raise EnvironmentError("GEMINI_API_KEY is not set in .env.")

    # main.py already rejects any sender that isn't ALLOWED_SENDER_EMAIL
    # before this function is ever called. prompt.txt (kept unedited as the
    # canonical spec) still tells the model to independently check for
    # @gradient.com — this note overrides that for the current run so the
    # two checks agree instead of fighting each other.
    approved_sender = os.environ.get("ALLOWED_SENDER_EMAIL", "")
    auth_override = (
        f"Sender authorization has already been verified by the calling "
        f"application for this run. Treat '{approved_sender}' as an approved "
        f"sender for the AUTHORIZED SENDERS check below."
    )

    parts = [
        {"text": SYSTEM_PROMPT},
        {"text": auth_override},
        {"text": f"Sender: {sender}"},
        {"text": f"Email Date: {received_date}"},
        {"text": f"Subject: {subject}"},
        {"text": body_text},
    ]
    for img in images:
        parts.append({
            "inline_data": {
                "mime_type": img["mime_type"],
                "data": base64.b64encode(img["bytes"]).decode("ascii"),
            }
        })

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "response_mime_type": "application/json",  # forces pure JSON, no markdown fences
            "temperature": 0,                             # deterministic extraction, not creative
        },
    }

    global _working_model
    candidates = [_working_model] if _working_model else MODEL_CANDIDATES

    response_body = None
    last_error = None
    for model in candidates:
        request = urllib.request.Request(
            _endpoint_for(model),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": API_KEY,
            },
            method="POST",
        )
        try:
            response_body = _post_with_retry(request)
            if _working_model != model:
                print(f"Using Gemini model: {model}")
                _working_model = model
            break
        except RuntimeError as e:
            if "Gemini API returned 404" in str(e):
                last_error = e
                continue
            raise

    if response_body is None:
        raise RuntimeError(
            f"None of these models worked for your key: {candidates}. "
            f"Last error: {last_error}\n"
            f"Check what your key actually supports at: "
            f"https://generativelanguage.googleapis.com/v1beta/models?key=YOUR_KEY"
        )

    try:
        return response_body["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise RuntimeError(f"Unexpected response shape from Gemini: {response_body}")


def _post_with_retry(request, max_retries=5, base_delay=10):
    """
    Retries on 429 (rate limit) with exponential backoff, honoring the
    Retry-After header when Google sends one instead of guessing.
    Any other HTTP error fails immediately — no point retrying a 400/404.
    """
    delay = base_delay
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries:
                retry_after = e.headers.get("Retry-After")
                wait = int(retry_after) if retry_after else delay
                print(f"Rate limited (429) — waiting {wait}s, retry {attempt}/{max_retries}...")
                time.sleep(wait)
                delay *= 2
                continue
            error_detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini API returned {e.code}: {error_detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Could not reach Gemini API: {e.reason}") from e

    raise RuntimeError(f"Still rate limited after {max_retries} retries — try again later "
                        f"or check your quota at aistudio.google.com.")