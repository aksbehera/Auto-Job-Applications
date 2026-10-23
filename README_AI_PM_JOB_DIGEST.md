# AI PM Job Digest — India

A recurring, private job-search pipeline for AI / Technical Product Manager roles.
It discovers live openings across India-relevant platforms via **Apify** (plus
AI-native companies' **ATS career pages**), de-dupes them, stores every role —
full job description included — in a **Google Sheet**, and emails a **curated,
grouped digest every two days**. Once a week it adds a **requirements analysis**
across all stored JDs.

Everything is private: discovery is read-only scraping, the Sheet is yours, and
the only output is an email to your own inbox. Nothing is ever posted anywhere,
and no employer is contacted.

> This system lives entirely in `job_digest/`, `config/`, `scripts/`,
> `run_scraper.py` and `.github/workflows/job-digest.yml`. It does **not** touch
> the legacy `Auto Job Application on Naukri_Github.ipynb` notebook at the repo root.

## How it works

```
discover            Apify actors (LinkedIn, Indeed, …) + ATS pages (Greenhouse/Lever/Ashby)
  → classify        rule-based: keep the lane, drop noise, tag tier/remote/seniority/group
  → recency         drop anything older than 14 days
  → dedupe (run)    collapse the same role seen on several platforms (best source wins)
  → dedupe (Sheet)  drop roles already stored — the Sheet is the memory
  → summarise       Claude writes a 2–3 sentence summary + parses key requirements (new roles only)
  → store           append every new role as a row in the Google Sheet
  → select          rank + group → Target-company, then Remote, then India on-site/hybrid (cap 25)
  → analyse         weekly: aggregate all JDs → common skills, bands, gaps vs your profile
  → email           one grouped HTML digest via Gmail SMTP; mark those roles "sent"
```

**The lane** (what it keeps), **exclusions**, **target companies + tiers**,
**locations**, **search queries** and **platforms** are all defined in
[`config/targets.yaml`](config/targets.yaml) — edit that, not the Python, to tune
the search. Your profile keywords for the gap analysis live in
[`config/profile.md`](config/profile.md).

## The Google Sheet (system of record)

All roles are stored in one Sheet — this is where you browse, filter and read full JDs:

> https://docs.google.com/spreadsheets/d/1mTNmTNJOnaUq-31XfapO36ZSY2CNLZP_7isq3KJTN3A/edit

Columns: `Date added · Source platform · Company · Tier · Title · Location ·
Remote? · Posted date · Seniority · Salary/comp · Short summary · Full JD ·
Key requirements/skills · Apply URL · Sent in digest? · Match score · Dedupe key`.
A hidden `_meta` tab tracks the weekly-analysis cadence. The email links here and
only summarises; full JDs stay in the Sheet.

## Setup

### 1. Python
```bash
pip install -r requirements.txt
cp .env.example .env      # fill in for local runs; in CI these are GitHub secrets
```

### 2. Google service account (for unattended Sheet writes)
1. In [Google Cloud Console](https://console.cloud.google.com/) create (or pick) a
   project and **enable the Google Sheets API and the Google Drive API**.
2. **IAM & Admin → Service Accounts → Create service account.** No roles needed.
3. On that service account, **Keys → Add key → JSON** and download the key file.
4. Open the key file and copy the `client_email` (looks like
   `something@your-project.iam.gserviceaccount.com`).
5. **Share the Google Sheet with that `client_email` as an Editor** (the Share
   button on the Sheet). *This is the step people forget — without it, writes 403.*
6. Provide the key to the pipeline:
   - **Local:** save the file (e.g. `service-account.sa.json`, already git-ignored)
     and set `GOOGLE_SERVICE_ACCOUNT_FILE=service-account.sa.json` in `.env`.
   - **GitHub Actions:** paste the **entire JSON** as the `GOOGLE_SERVICE_ACCOUNT_JSON` secret.

Verify it:
```bash
GOOGLE_SERVICE_ACCOUNT_FILE=service-account.sa.json python scripts/check_sheet.py
```
It prints the service-account email, confirms access, and creates the header row.

### 3. Apify (job discovery)
Create an [Apify](https://apify.com/) account with credits and copy your API token
(**Settings → Integrations → API token**). Set `APIFY_TOKEN`. LinkedIn + Indeed are
enabled by default. Before trusting a platform, confirm its actor parses correctly:
```bash
APIFY_TOKEN=... python scripts/test_apify.py linkedin "AI Product Manager"
APIFY_TOKEN=... python scripts/test_apify.py indeed   "AI Product Manager"
```
If a field shows up blank/MISSING, add the real output key to that platform's
`fields` map in `config/targets.yaml`.

### 4. Claude API (summaries + weekly analysis)
Set `ANTHROPIC_API_KEY`. Model defaults to `claude-sonnet-4-5` (override with
`SUMMARY_MODEL`). Costs are small — one short call per *new* role plus one weekly call.

### 5. Gmail (sending the digest)
On the sender Google account (with 2-Step Verification on), create an
[app password](https://myaccount.google.com/apppasswords). Set `GMAIL_ADDRESS`
and `GMAIL_APP_PASSWORD`. `DIGEST_RECIPIENT` defaults to `aksbehera@gmail.com`.

## Running

```bash
python run_scraper.py                 # full run: discover, store, email
python run_scraper.py --dry-run       # render out/digest.html; no Sheet write, no email
python run_scraper.py --no-apify      # ATS career pages only (free; skip paid actors)
python run_scraper.py --no-ats        # Apify platforms only
python run_scraper.py --no-llm        # skip summaries/analysis (fallback text)
```

A dry run needs **no credentials** (it skips the Sheet and renders this run's finds
to `out/digest.html`) — the quickest way to preview the email.

## Scheduling (GitHub Actions)

[`.github/workflows/job-digest.yml`](.github/workflows/job-digest.yml) runs **every
2 days at 03:30 UTC (09:00 IST)**. Add these **Actions secrets** (Settings →
Secrets and variables → Actions):

| Secret | What |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key |
| `APIFY_TOKEN` | Apify API token |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | the full service-account JSON |
| `GMAIL_ADDRESS` | sender Gmail address |
| `GMAIL_APP_PASSWORD` | Gmail app password |
| `JOBS_SHEET_ID` | *(optional)* override the target Sheet |

Recipients are set in the workflow's `DIGEST_RECIPIENT` env (plain addresses,
comma-separated — not a secret). You can also:
- **Run on demand:** Actions → *AI PM Job Digest* → *Run workflow* (with an optional
  dry-run / no-Apify toggle), **or** commit any change to `.github/fire-digest`
  (`date > .github/fire-digest && git commit -am fire && git push`). Ordinary code
  pushes never send a digest.

The Sheet is the system of record, so the workflow commits nothing back.

## Tuning

- **Add/enable platforms** — Naukri, Foundit, Wellfound, Instahyre and Glassdoor are
  pre-wired but **disabled**; set `enabled: true` and a confirmed `actor` id in
  `config/targets.yaml`, then validate with `scripts/test_apify.py`.
- **ATS slugs vary** — each AI-native company's board slug in `ats_boards` should be
  confirmed (a wrong slug just 404s and is skipped with a footer note). Working slugs
  pull the cleanest full JDs with direct apply links, for free.
- **Widen/narrow the net** — edit `search_queries`, `target_titles`, `exclude_titles`,
  `companies`, `recency_days`, `max_items_per_digest`.
- **Sharpen the gap analysis** — keep `config/profile.md`'s keyword list matching your
  actual resume/LinkedIn.

## Resilience

Every source is fail-soft: if an actor or ATS board errors, it's skipped for that run
and listed in the digest footer rather than failing the whole run. Each run logs
`found / new / sent` counts (in the logs and the email footer).
