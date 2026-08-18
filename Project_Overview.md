# Project Documentation|Financial Statement Extraction POC|

Complete record of what this project is, how it evolved, and exactly how it works
today. Written so you (or anyone else) could pick this up cold and understand it.

---

## 1. The goal

You provided a system prompt (saved as `prompt.txt`) that defines an "Enterprise
Financial Document Understanding Agent": given one email (text + one or more bank
statement images), it should:

- Reject the email outright if the sender isn't authorized
- Associate each image with the correct bank using nearby heading text
- Extract a fixed set of fields per statement (account holder, balances, dates,
  reference numbers, etc.) — `null` for anything not clearly visible, never guessed
- Tag every extracted field with a confidence level (HIGH/MEDIUM/LOW)
- Compare the email's received date against the statement's date and report
  MATCH / DATE_MISMATCH / UNKNOWN
- Return nothing but the exact JSON schema specified — no prose, no extra fields

The project's job is to actually run that prompt against real Gmail messages:
pull the email, hand its text and images to Gemini along with the prompt, and
save the resulting JSON.

---

## 2. How we got to the current design (the decision trail)

This went through several pivots, each one forced by something that failed in
practice rather than a preference. Worth knowing why, so nothing gets "fixed"
back into a version that didn't work:

| Step | Tried | Problem | Resolution |
|---|---|---|---|
| 1 | Microsoft Graph API (Outlook) with an Azure AD app registration | Registering an app requires Azure tenant admin rights, which you don't have | Dropped Outlook, moved to Gmail |
| 2 | Gmail API via OAuth (Google Cloud Console project) | Google Cloud Console started demanding a linked billing account before letting the project proceed | Dropped the Gmail *API*, kept Gmail — switched to plain **IMAP with an App Password**, which needs no Google Cloud project at all |
| 3 | Gemini via the `google-genai` SDK | The SDK pulls in `google-auth` → `cryptography`, which ships a compiled Rust binary. Your machine's Windows Application Control policy blocked that binary outright | Dropped the SDK entirely — `gemini_client.py` now calls the Gemini REST API directly over plain HTTPS using only Python's built-in `urllib` |
| 4 | Sender check scoped to the `gradient.com` domain (as written in `prompt.txt`) | You only need a single specific Gmail address allowed, not a whole domain | Added `ALLOWED_SENDER_EMAIL` as an exact-match config value; `prompt.txt` itself was left untouched as the canonical spec, and `gemini_client.py` sends Gemini a one-line runtime note so its own internal domain check doesn't fight the app's check |
| 5 | Model: `gemini-3.6-flash` | Hit a rate limit after a single call — newer preview models ship with much tighter free-tier caps | Tried switching to `gemini-2.5-flash` |
| 6 | Model: `gemini-2.5-flash` | Google returned `404: This model ... is no longer available to new users` — it was deprecated for new API keys ahead of an Oct 16, 2026 shutdown | Replaced the single hardcoded model with a **candidate list** (`MODEL_CANDIDATES`) that's tried in order; whichever one actually works for your key gets cached and reused for the rest of the run, so this class of breakage self-heals instead of requiring another manual fix |
| 7 | (Ongoing risk) Gemini free-tier rate limits | Even the right model can still return 429 under bursts | Added retry-with-exponential-backoff, honoring Google's `Retry-After` header when present |
| 8 | Real test data | Free-tier Gemini usage may be used to improve Google's models — not something to risk with real bank data | Generated fully synthetic sample bank statement images (Maybank/UOB/AmBank) with a visible watermark, for testing only |

Net effect: **zero cost, zero third-party compiled binaries, zero Google Cloud
Console dependency, self-recovering model selection.**

---

## 3. Final architecture

```
Gmail inbox (yours)
      │  IMAP (App Password, read-only) — no Google Cloud project involved
      ▼
imap_client.py   — connect, search by sender, fetch full message
      │
      ▼
email_utils.py   — exact sender-address check; walk the MIME tree for
      │              plain-text body + image attachments/inline images
      ▼
gemini_client.py — build the request (system prompt + sender/date/body +
      │              base64 images), POST to Gemini over plain urllib,
      │              trying candidate models until one works, retrying on 429
      ▼
main.py          — orchestrates the above per email, parses the JSON
      │              response, writes it to disk
      ▼
output/<message-id>.json
```

---

## 4. Every file, and what it actually does

```
statement-poc/
├── README.md              Setup + troubleshooting instructions (user-facing)
├── requirements.txt        2 packages: python-dotenv, beautifulsoup4 — nothing
│                            with a compiled extension, deliberately
├── .env.example             Template for your secrets (never commit the real .env)
├── .gitignore
├── prompt.txt                The system prompt, unedited from your original spec —
│                              loaded and sent to Gemini verbatim on every call
├── imap_client.py             Gmail connection over IMAP:
│                              - connect(): logs in with GMAIL_ADDRESS + GMAIL_APP_PASSWORD
│                              - search_messages(): server-side FROM filter (cheap pre-filter)
│                              - fetch_message(): pulls the full RFC822 message
├── email_utils.py              Parses a fetched message:
│                              - is_authorized_sender(): exact match against
│                                ALLOWED_SENDER_EMAIL (case-insensitive)
│                              - get_body_and_images(): walks the MIME tree,
│                                returns plain-text body + list of
│                                {filename, mime_type, bytes} for every image part
├── gemini_client.py             Talks to Gemini with zero SDK:
│                              - MODEL_CANDIDATES: ordered list of model IDs to try
│                              - extract_statements(): builds the parts list
│                                (prompt + auth-override note + sender/date/body
│                                + base64-encoded images), loops candidates on 404,
│                                caches whichever model works
│                              - _post_with_retry(): the actual HTTP call, with
│                                exponential backoff on 429
├── main.py                       Orchestration: connect → search → for each
│                              message, check sender → extract body/images →
│                              call Gemini → parse JSON → write to output/
└── output/                        One <message-id>.json per successfully
                               processed email lands here at runtime
```

Also produced along the way (not part of the running pipeline, but part of this
project): a small standalone script that generates synthetic test bank-statement
PNGs (Maybank, UOB, AmBank — the three you handed me as sample images), used to
exercise the pipeline without risking real financial data on the free tier.

---

## 5. Complete setup, from zero

1. **Install Python 3.10+** if you don't have it.
2. **Install dependencies:**
   ```bash
   cd statement-poc
   python -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. **Turn on 2-Step Verification** on the Gmail account you're using, at
   `myaccount.google.com/security` (required before Google will issue App Passwords).
4. **Generate a Gmail App Password** at `myaccount.google.com/apppasswords`.
   Copy the 16-character password — it's shown once.
5. **Get a free Gemini API key** at `aistudio.google.com` → Get API key. No card.
   (If it ever offers to "set up billing," don't — that removes the free tier
   for that project.)
6. **Configure `.env`:**
   ```bash
   cp .env.example .env
   ```
   Fill in:
   ```
   GMAIL_ADDRESS=you@gmail.com
   GMAIL_APP_PASSWORD=the16charpassword
   ALLOWED_SENDER_EMAIL=sender@gmail.com
   GEMINI_API_KEY=your-gemini-key
   ```
7. **Add test data:** send yourself an email from exactly `ALLOWED_SENDER_EMAIL`,
   attaching the synthetic sample statement images, with bank-name headings in
   the body text between each image (matching the pattern `prompt.txt` expects).
8. **Run it:**
   ```bash
   python main.py
   ```

---

## 6. What happens when you run `python main.py` (step by step)

1. Loads `.env`, confirms `ALLOWED_SENDER_EMAIL` is set.
2. Opens an IMAP connection to Gmail using the App Password.
3. Searches the inbox for messages from `ALLOWED_SENDER_EMAIL` (server-side,
   cheap pre-filter — up to 10 most recent).
4. For each matching message:
   - Fetches the full message.
   - **Re-checks** the sender address exactly (the IMAP search is a loose
     substring match; this is the real gate).
   - If unauthorized → prints a skip message, moves on. **No Gemini call made.**
   - Walks the MIME structure to pull out the plain-text body and every image
     part (attachment or inline).
   - If no images found → warns and skips (nothing useful to send Gemini).
   - Builds the Gemini request: your full `prompt.txt`, a note confirming the
     sender's already been verified, the sender/date/body text, and every
     image base64-encoded inline.
   - Sends it to Gemini, trying each candidate model in order until one
     doesn't 404, retrying with backoff on 429.
   - Parses the returned text as JSON.
   - Writes it to `output/<message-id>.json`.
   - Prints a one-line summary (`OK: 'subject' -> N statement(s) -> path`).
5. Logs out of IMAP.

---

## 7. Testing checklist

Verify all four before trusting the output:

1. **Unauthorized sender** — an email not from `ALLOWED_SENDER_EMAIL` is skipped,
   no Gemini call made.
2. **Multi-bank association** — one email with images under different bank
   headings produces separate `statements` entries with the right bank each.
3. **Nulls on unreadable fields** — a deliberately degraded image (the AmBank
   sample has a blurred account holder name) returns `null` for that field,
   not a guess.
4. **Date validation** — matching vs. mismatched email/statement dates return
   `MATCH` / `DATE_MISMATCH` correctly.

---

## 8. Known limitations (intentionally out of scope for a POC)

- **On-demand only** — this fetches when you run it manually; real-time
  monitoring would need Gmail push notifications (which *does* require Google
  Cloud, unlike everything else here).
- **Local secrets** — `.env` on disk is fine for a POC, not for production.
- **No database** — output is local JSON files.
- **No human review step** before any downstream use of extracted numbers.
- **Free-tier data use** — Google may use free-tier prompts/files to improve
  their models. Real customer statements shouldn't go through this until
  you're on a paid tier with different data terms.
- **Model IDs will drift again** — Google retires Gemini model names
  regularly (this project already hit it twice). `MODEL_CANDIDATES` in
  `gemini_client.py` absorbs this automatically as long as at least one
  candidate in the list is still valid; if all of them ever die at once,
  check `https://generativelanguage.googleapis.com/v1beta/models?key=YOUR_KEY`
  for what your key currently supports and add it to the list.