# Financial Statement Extraction Agent

> **Status:** Proof of Concept — not production-ready. See [Limitations](#limitations).

Reads bank-statement images out of a Gmail inbox and turns them into structured,
schema-validated JSON using Gemini — sender whitelisting, per-bank association,
confidence scoring, and a strict never-guess policy, all defined in [`prompt.txt`](prompt.txt).

Built to run at **zero cost**: no Google Cloud Console project, no billing account,
no SDK with compiled native dependencies. Just an IMAP login and a Gemini API key.

---

## Contents

- [How it works](#how-it-works)
- [Why it's built this way](#why-its-built-this-way)
- [Setup](#setup)
- [Configuration](#configuration)
- [Running it](#running-it)
- [Sample test data](#sample-test-data)
- [Testing checklist](#testing-checklist)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [Security & data handling](#security--data-handling)

---

## How it works

```
Gmail inbox
      │  IMAP (App Password, read-only) — no Google Cloud project involved
      ▼
imap_client.py    connect, search by sender, fetch full message
      │
      ▼
email_utils.py    exact sender check; walk the MIME tree for body text + images
      │
      ▼
gemini_client.py  build the request (prompt.txt + sender/date/body + images),
      │           POST to Gemini over plain urllib — tries a list of model IDs
      │           until one works, retries on rate limits
      ▼
main.py           orchestrates all of the above, writes results to disk
      ▼
output/<message-id>.json
```

For each email: verify the sender is on the allow-list, pull out the body text
and every image attachment, hand it all to Gemini alongside the system prompt,
and save whatever comes back as JSON. Nothing more.

---

## Why it's built this way

A few choices here aren't the "default" way to do this, each for a concrete reason:

- **IMAP + App Password instead of the Gmail API.** The Gmail API route requires
  a Google Cloud Console project, which started demanding a linked billing
  account before letting new projects proceed. IMAP needs none of that.
- **Raw HTTPS (`urllib`) instead of the `google-genai` SDK.** The SDK pulls in
  `google-auth` → `cryptography`, which ships a compiled Rust binary. On
  locked-down Windows machines, Application Control / WDAC policies can block
  that binary outright. This project has zero third-party packages with
  compiled extensions in its core dependency chain.
- **A model candidate list instead of one hardcoded model name.** Google
  retires Gemini model IDs on a schedule this project can't keep up with by
  hand — it's already hit two dead model names in testing. `gemini_client.py`
  tries a short list in order and remembers whichever one actually works for
  your key, so this failure mode is self-healing instead of a manual fix
  every time.

Full decision-by-decision history (what was tried, what broke, what replaced
it) is in [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) if you want the whole story.

---

## Setup

**Prerequisites:** Python 3.10+, a Gmail account. Nothing else — no admin
approval, no card, no Cloud project.

```bash
git clone <this-repo>
cd statement-poc
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**1. Turn on 2-Step Verification** on the Gmail account you're using:
`myaccount.google.com` → Security → 2-Step Verification. Required before
Google will issue App Passwords.

**2. Generate a Gmail App Password:** `myaccount.google.com/apppasswords` →
name it anything → copy the 16-character password shown (it's shown once).
This is scoped to mail access only, not your real password, and revocable
any time from the same page.

**3. Get a free Gemini API key:** `aistudio.google.com` → Get API key →
Create API key. No card required for the free tier. *(If AI Studio ever
offers to "set up billing," don't — that removes the free tier entirely for
that project.)*

**4. Configure environment:**

```bash
cp .env.example .env
```

Fill in the four values — see [Configuration](#configuration) below.

---

## Configuration

All config lives in `.env` (copy from `.env.example`, never commit the real file):

| Variable | Description |
|---|---|
| `GMAIL_ADDRESS` | The Gmail inbox to read from |
| `GMAIL_APP_PASSWORD` | 16-character App Password (not your real Gmail password) |
| `ALLOWED_SENDER_EMAIL` | The *only* address this agent accepts emails from — exact match, not a domain. Anything else is skipped as `UNAUTHORIZED_SENDER` before any Gemini call is made |
| `GEMINI_API_KEY` | Free-tier key from Google AI Studio |

---

## Running it

```bash
python main.py
```

No browser popup, no login flow — connects straight over IMAP. Output lands
as one JSON file per processed email in `output/`, named by message ID.
Console output shows what was processed and what was skipped, and why.

---

## Sample test data

`sample_data/` has three ready-to-use synthetic bank statement images
(Maybank, UOB, AmBank) — fully fictional data, watermarked "SAMPLE / TEST DATA."
`ambank_sample_degraded.png` has a deliberately blurred field, for testing
the null-on-unreadable-field behavior.

Send yourself one email from `ALLOWED_SENDER_EMAIL`, attach all three, and
put the bank name as a heading before each image in the body — matching the
pattern `prompt.txt` expects:

```
Maybank
[attach maybank_sample.png]

UOB
[attach uob_sample.png]

AmBank
[attach ambank_sample_degraded.png]
```

Want different data? `scripts/generate_sample_statements.py` regenerates
these (or new variants — edit the calls at the bottom of the file). It needs
Pillow (`pip install -r requirements-dev.txt`), which is **not** part of the
core pipeline's dependencies for the same compiled-binary reason described
above — if that install also gets blocked on your machine, just use the
images already provided.

---

## Testing checklist

1. **Unauthorized sender** — an email not from `ALLOWED_SENDER_EMAIL` is
   skipped, no Gemini call made.
2. **Multi-bank association** — one email, multiple images under different
   bank headings, produces separate `statements` entries with the right
   bank each.
3. **Nulls on unreadable fields** — a degraded image returns `null` for that
   field rather than a guess.
4. **Date validation** — matching vs. mismatched email/statement dates
   return `MATCH` / `DATE_MISMATCH` correctly.

---

## Project structure

```
statement-poc/
├── README.md
├── PROJECT_OVERVIEW.md          full build history and design rationale
├── requirements.txt               core deps: python-dotenv, beautifulsoup4
├── requirements-dev.txt            optional: Pillow, for the sample-data generator only
├── .env.example
├── .gitignore
├── prompt.txt                       the system prompt sent to Gemini, verbatim
├── imap_client.py                    Gmail IMAP connection
├── email_utils.py                     sender check, body/image extraction
├── gemini_client.py                    Gemini calls over plain HTTPS, model fallback, retry
├── main.py                              entry point — run this
├── scripts/
│   └── generate_sample_statements.py     synthetic test-data generator
├── sample_data/                            ready-to-use test images
└── output/                                  extraction results land here
```

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `[AUTHENTICATIONFAILED] Invalid credentials` | Using your real Gmail password instead of the App Password, or 2-Step Verification isn't on yet |
| `GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set` | `.env` wasn't created from `.env.example`, or values weren't filled in |
| `ALLOWED_SENDER_EMAIL is not set` / `KeyError: 'GEMINI_API_KEY'` | Same as above, for those specific values |
| Everything skipped as "unauthorized sender" | `ALLOWED_SENDER_EMAIL` must match the test email's From address *exactly* — no display-name or domain matching |
| App Password option missing from your Google Account | Happens on Workspace (school/work) accounts where an admin disabled it, or with Advanced Protection enabled — use a personal `@gmail.com` account |
| `Gemini API returned 404` for every candidate | All models in `MODEL_CANDIDATES` (`gemini_client.py`) are dead. Check what your key currently supports at `https://generativelanguage.googleapis.com/v1beta/models?key=YOUR_KEY` and add the current name to the list |
| Model returns non-JSON / truncated JSON | Possible free-tier rate limit — the script retries on 429 automatically, but check live limits at aistudio.google.com if it keeps happening |
| `ImportError: DLL load failed ... Application Control policy has blocked this file` | Leftover `google-genai`/`cryptography` install from an earlier attempt — this version doesn't import that SDK at all. Run `pip uninstall google-genai google-auth cryptography` and reinstall from `requirements.txt` |
| No emails found | Confirm test emails are in the Inbox (not archived/spam) and actually sent from `ALLOWED_SENDER_EMAIL` |

---

## Limitations

Intentionally out of scope for a POC:

- **On-demand only** — fetches when you run it manually; real-time monitoring
  would need Gmail push notifications, which *does* require Google Cloud
  (unlike everything else here).
- **Local secrets** — `.env` on disk is fine for a POC, not production.
- **No database** — output is local JSON files.
- **No human review step** before any downstream use of extracted numbers.
- **Model IDs will drift again** — `MODEL_CANDIDATES` absorbs this as long as
  at least one entry is still valid; if all of them die at once, see the
  Troubleshooting table above.

---

## Security & data handling

- **Free-tier Gemini usage may be used by Google to improve their models.**
  Don't run real customer financial documents through this while it's on the
  free tier — the `sample_data/` images exist so you don't have to.
- `.env`, `credentials.json`-style files, and anything with real secrets are
  gitignored — double check before committing if you add new config.
- The sender allow-list (`ALLOWED_SENDER_EMAIL`) is enforced in Python
  *before* any data is sent to Gemini — an unauthorized email never leaves
  this codebase.