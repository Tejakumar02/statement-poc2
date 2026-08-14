# Financial Statement Extraction POC

Reads bank-statement images out of a Gmail inbox and turns them into structured JSON
using Gemini, following the rules in `prompt.txt` (sender whitelist, supported banks,
never-guess policy, confidence scoring, etc.).

**This version never touches Google Cloud Console, and calls Gemini over
plain HTTPS instead of Google's SDK.** Email is read over IMAP with a Gmail
App Password (a native Gmail feature, not a workaround), and `gemini_client.py`
uses only Python's built-in `urllib` — no `google-genai` package. That matters
if you're on a locked-down Windows machine: the SDK pulls in `google-auth`,
which pulls in `cryptography`, which ships a compiled Rust binary that
Application Control / WDAC policies on managed machines often block outright.
This project has zero third-party packages that ship compiled binaries.

---

## Project layout

```
statement-poc/
├── README.md
├── requirements.txt
├── .env.example         <- copy to .env and fill in your values
├── .gitignore
├── prompt.txt             <- the system prompt sent to Gemini (your rules/schema)
├── imap_client.py          <- connects to Gmail over IMAP with an App Password
├── email_utils.py           <- sender check, body text + image extraction
├── gemini_client.py          <- calls Gemini over plain HTTPS (stdlib only, no SDK)
├── main.py                    <- orchestrates the whole pipeline, run this
└── output/                     <- one JSON file per processed email lands here
```

---

## ⚠️ Two things to know before you start

1. **Free Gemini tier + real data don't mix.** Google may use free-tier prompts/files
   to improve their models. Use your own test emails with fake/sample statement
   images while this is on the free tier — not real customer documents.

2. **Don't enable billing on your Gemini project "just to be safe."** As of 2026,
   turning on billing removes the free tier entirely for that project — every
   call becomes billable from the first token, even ones that would've fit
   inside the free quota. If AI Studio ever shows a "Set up billing" prompt,
   skip it unless you've deliberately decided to pay.

---

## Prerequisites

- Python 3.10+
- A Gmail account
- 5 minutes for one-time setup below

No Google Cloud project, no card, no admin approval needed.

---

## Setup

### 1. Install dependencies

```bash
cd statement-poc
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Turn on 2-Step Verification (if not already on)

Go to **myaccount.google.com → Security → 2-Step Verification** and turn it on.
This is required before Google will let you generate an App Password.

### 3. Generate a Gmail App Password

1. Go to **myaccount.google.com/apppasswords**.
2. App name: anything, e.g. `statement-poc`.
3. Google shows you a 16-character password — copy it now, it won't be shown again.

This password is scoped to IMAP/mail access only — it's not your real Gmail password,
and you can revoke it any time from the same page.

### 4. Get a Gemini API key

1. Go to **aistudio.google.com** → sign in → **Get API key** → **Create API key**.
2. No credit card needed for the free tier.

### 5. Configure environment

```bash
cp .env.example .env
```

Fill in `.env`:
```
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=the16charpassword
ALLOWED_SENDER_EMAIL=sender@gmail.com
GEMINI_API_KEY=your-gemini-key
```

`ALLOWED_SENDER_EMAIL` is the one address this agent will accept emails from —
an exact match, not a domain. Everything else gets skipped as `UNAUTHORIZED_SENDER`.
It can be the same as `GMAIL_ADDRESS` (you emailing test statements to yourself)
or a different address entirely — whichever you're actually sending test emails from.

### 6. Add test emails

Send 2–3 emails **from exactly the address in `ALLOWED_SENDER_EMAIL`** to the
inbox in `GMAIL_ADDRESS`. Each email should have 1+ statement-style images,
ideally with a bank name written near each image.

---

## Run it

```bash
python main.py
```

No browser popup, no login flow — it connects straight over IMAP using the
App Password from `.env`.

Output: one JSON file per processed email in `output/`. Console output shows
what was skipped and why.

---

## Testing checklist

Don't consider this "done" until you've verified all four:

1. **Unauthorized sender** → an email not from `ALLOWED_SENDER_EMAIL` is skipped, no Gemini call made.
2. **Correct bank association** → an email with two statement images under two different
   bank headings produces two separate `statements` entries with the right bank each.
3. **Nulls on unreadable fields** → a deliberately blurry/cropped test image returns
   `null` rather than a guessed value.
4. **Date validation** → matching vs. mismatched email/statement dates correctly
   return `MATCH` / `DATE_MISMATCH`.

---

## Troubleshooting

- **`imaplib.IMAP4.error: b'[AUTHENTICATIONFAILED] Invalid credentials'`** →
  you're using your normal Gmail password instead of the App Password, or
  2-Step Verification isn't actually turned on yet.
- **`GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set`** → `.env` wasn't created
  from `.env.example`, or the values weren't filled in.
- **`KeyError: 'GEMINI_API_KEY'`** / **`ALLOWED_SENDER_EMAIL is not set`** →
  `.env` is missing that value — check it was copied from `.env.example` and filled in.
- **Everything gets skipped as "unauthorized sender"** → `ALLOWED_SENDER_EMAIL` must
  match the test email's From address *exactly* (case doesn't matter, but the address
  does) — no display-name matching, no domain matching.
- **App Password option missing from your Google Account** → this happens on
  Workspace (school/work) accounts where an admin has disabled it, or if
  Advanced Protection is enabled on the account. Use a personal @gmail.com
  account for this POC if that's the case.
- **Model returns non-JSON / truncated JSON** → check you're not hitting the
  free-tier rate limit (live limits shown at aistudio.google.com); the script
  prints the raw response so you can see what came back.
- **`ImportError: DLL load failed ... Application Control policy has blocked
  this file`** → this was the old `google-genai` SDK's `cryptography`
  dependency getting blocked by Windows Application Control on a managed
  machine. This version doesn't use that SDK at all (see `gemini_client.py`),
  so if you still see this, run `pip list` and check `google-genai` isn't
  installed in this venv from an earlier attempt — if it is, `pip uninstall
  google-genai google-auth cryptography` and reinstall from `requirements.txt`.
- **`Gemini API returned 404: ...`** → the model name in `gemini_client.py`
  (`MODEL = "..."`) has been retired or renamed. Check aistudio.google.com
  for the current free-tier model name and update that one line.
- **No emails found** → confirm the test emails are in the Inbox (not archived/spam)
  and the sender address actually contains the domain you're filtering on.

---

## What's intentionally out of scope for this POC

- Continuous monitoring (this fetches on-demand when you run the script; real-time
  would need Gmail push notifications, which does require Google Cloud)
- Production-grade credential storage (`.env` on disk is fine for a POC, not for production)
- Retry/backoff on Gemini rate limits
- Database storage (currently just local JSON files)
- A human review step before any downstream use of extracted numbers
