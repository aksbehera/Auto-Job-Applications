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
discover            Apify actors (LinkedIn, Indeed, …) + ATS pages (Greenhouse/Ashby)
  → pre-filter      cheap keyword lane + tag tier/remote/seniority (keeps the candidate set small)
  → recency         drop anything older than 14 days
  → dedupe (run)    collapse the same role (company+title, location-independent); best source wins
  → dedupe (Sheet)  drop roles already stored — the Sheet is the memory
  → SCORE           Claude reads each JD and returns a 0–100 fit score + 6 sub-scores,
                    a summary, requirements, the biggest fit reason and gap/risk (new roles only)
  → store           append roles scoring ≥55 (Marginal+) to the Sheet; drop Low
  → rank            strictly by match score; split takeable shortlist vs aspirational (relocation+visa)
  → analyse         weekly: aggregate all JDs → common skills, bands, gaps vs your profile
  → email           takeable roles ≥70 up top, aspirational international parked below; HTML via Gmail SMTP
```

**The lane**, **target companies + tiers**, **locations**, **search queries**,
**platforms** and **ATS boards** are defined in
[`config/targets.yaml`](config/targets.yaml). Your candidate profile — which the
scorer judges every JD against — is [`config/profile.md`](config/profile.md); keep
it accurate, it's the heart of the match score.

## The match score

Every role gets a **0–100 fit score** from an LLM that reads the **full JD**
against your profile — judging the *kind* of role by its must-haves, not its
title. Six weighted dimensions: **role-type (30)**, domain (20), seniority (15),
company (15), location (15), feasibility (5). Seniority and company also carry
the level/comp signal (a role scoped PM I/II or at an IT-services delivery shop
scores down even with perfect AI fit).

**Takeability is decisive.** Each role is judged *takeable from India now* (India
located, or remote and India-eligible) or not (international on-site,
US-state-locked, or US-only "remote" with no stated India hiring/visa). A
not-takeable role is capped at 60 so it **can never read as Strong** — company
prestige doesn't change takeability — and is tagged `relocation + visa required`.

Hard caps: code-gated / ML-eng / data-architect / non-AI-PM → 15
(`excluded-role-type`); unmet hard must-have → 30 (blocker named); not takeable →
60. Bands: **Strong 85+ (and takeable) · Good 70–84 · Marginal 55–69 · Low <55**.

The email has two parts: the **actionable shortlist** (takeable, score ≥70,
ranked) and, parked at the bottom, **aspirational** international roles (not
takeable but strong on paper, uncapped fit ≥70). Marginal stays in the Sheet;
Low is dropped. A role scored on a partial/absent JD is tagged `provisional`.
Tune thresholds in `job_digest/config.py`.

## The Google Sheet (system of record)

All roles are stored in one Sheet — this is where you browse, filter and read full JDs:

> https://docs.google.com/spreadsheets/d/1mTNmTNJOnaUq-31XfapO36ZSY2CNLZP_7isq3KJTN3A/edit

Columns: `Date added · Source platform · Company · Tier · Title · Location ·
Remote? · Posted date · Seniority · Salary/comp · Match score · Band ·
Top fit reason · Top gap/risk · Short summary · Key requirements/skills · Full JD ·
Apply URL · Sent in digest? · Role-type · Domain · Seniority score · Company score ·
Location score · Feasibility · Rationale · Dedupe key` (the six sub-scores are kept
for transparency and tuning). A hidden `_meta` tab tracks the weekly-analysis
cadence. The email links here and only summarises; full JDs stay in the Sheet.

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

**Verified actors (enabled by default):** LinkedIn `bebity~linkedin-jobs-scraper`,
Indeed `misceres~indeed-scraper`, Naukri `muhammetakkurtt~naukri-job-scraper`,
Foundit `themineworks~foundit-jobs-scraper`, Instahyre
`getascraper~instahyre-jobs-scraper`, Wellfound `memo23~wellfound-jobs-scraper`.
Glassdoor is wired but off. (Foundit returns lead metadata + apply link but not
the full JD text; the other five return full JDs.)

**ATS boards (free, no Apify):** all verified live — Greenhouse for Databricks,
Anthropic, Glean (`gleanwork`), Gong (`gongio`), Observe.ai (`observeai`), Cresta;
Ashby for Sierra, Decagon, OpenAI, ElevenLabs, Cognition, Writer, Cohere, Mistral
(`mistral.ai`), Runway (`runway-ml`), Perplexity. Clari has no public board (its
careers page redirects off-domain), so it's covered only via LinkedIn/Naukri.

**Cost control.** Every actor is pay-per-event, so each run costs Apify credits
and cost scales with `search_queries × platforms × results-per-run`. The defaults
are modest (5 queries, ~12 results each; Naukri's actor forces a 50 minimum). To
spend less: trim `search_queries`, lower each platform's `rows`/`maxItems`/`maxJobs`,
or set `enabled: false` on platforms you don't need. Watch your first few runs on
the [Apify console](https://console.apify.com/) and dial from there — the ATS
boards are always free.

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
