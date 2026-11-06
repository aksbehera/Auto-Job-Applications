"""End-to-end pipeline:

  discover → pre-filter (lane + metadata) → recency → dedupe (collapse)
  → dedupe vs Sheet → LLM match-score (full JD) → store (Marginal+, drop Low)
  → split takeable shortlist vs aspirational international → email → mark sent.

The Google Sheet is the system of record and the dedupe memory, so a role is
never re-scored, re-stored, or re-emailed.
"""

import logging
import time

from . import classify, dedup, discovery, emailer, ranking, requirements, scoring
from .config import (ASPIRATIONAL_THRESHOLD, OUT_DIR, SEND_THRESHOLD,
                     STORE_THRESHOLD, load_settings)
from .models import Job

log = logging.getLogger(__name__)

ASPIRATIONAL_CAP = 8   # how many not-takeable "strong on paper" roles to park at the bottom


def _recent(ts: float, recency_days: int) -> bool:
    return not (ts and (time.time() - ts) > recency_days * 86400)


def _int(v) -> int:
    try:
        return int(float(v or 0))
    except (ValueError, TypeError):
        return 0


def _row_to_job(row: dict, settings) -> Job:
    posted = str(row.get("Posted date", "")).strip()
    posted_ts = 0.0
    if posted:
        try:
            posted_ts = time.mktime(time.strptime(posted, "%Y-%m-%d"))
        except ValueError:
            posted_ts = 0.0
    tier = str(row.get("Tier", "")).strip()
    tier = "" if tier in ("", "—") else tier
    band_cell = str(row.get("Band", "")).strip()
    provisional = "provisional" in band_cell.lower()
    band = band_cell.split("·")[0].strip()
    return Job(
        source=str(row.get("Source platform", "")),
        company=str(row.get("Company", "")),
        title=str(row.get("Title", "")),
        location=str(row.get("Location", "")),
        url=str(row.get("Apply URL", "")),
        description="",
        posted_ts=posted_ts,
        salary=str(row.get("Salary/comp", "")),
        seniority=str(row.get("Seniority", "")),
        remote=str(row.get("Remote?", "")).strip().lower() == "yes",
        tier=tier,
        match_score=_int(row.get("Match score")),
        raw_score=_int(row.get("Raw score")),
        band=band,
        takeable=str(row.get("Takeable", "Yes")).strip().lower() != "no",
        provisional=provisional,
        summary=str(row.get("Short summary", "")),
        fit_reason=str(row.get("Top fit reason", "")),
        gap_risk=str(row.get("Top gap/risk", "")),
        dedupe_key=str(row.get("Dedupe key", "")),
    )


def _select(candidates, settings):
    takeable = ranking.select_takeable(candidates, settings.max_items_per_digest, SEND_THRESHOLD)
    aspirational = ranking.select_aspirational(candidates, ASPIRATIONAL_CAP, ASPIRATIONAL_THRESHOLD)
    return takeable, aspirational


def run(profile: str | None = None, dry_run: bool = False, use_apify: bool = True,
        use_ats: bool = True, use_llm: bool = True) -> int:
    settings = load_settings(profile)
    log.info("Profile: %s → Sheet %s, recipient %s",
             settings.profile, settings.sheet_id or "(unset)", settings.digest_recipient or "(unset)")

    disc = discovery.discover(settings, use_apify=use_apify, use_ats=use_ats)
    counts = dict(disc.counts)
    counts["_found"] = len(disc.jobs)

    laned = classify.classify(disc.jobs, settings)
    laned = [j for j in laned if _recent(j.posted_ts, settings.recency_days)]
    deduped = dedup.dedupe_batch(laned)

    client = _anthropic_client() if use_llm else None

    if dry_run:
        scoring.score_jobs(client, deduped, settings)
        counts["_new"] = len(deduped)
        takeable, aspirational = _select(deduped, settings)
        counts["_sent"] = len(takeable) + len(aspirational)
        _write_dry(takeable, aspirational, "", disc.skipped, counts, settings)
        return len(takeable) + len(aspirational)

    from .sheet import JobSheet
    sheet = JobSheet(settings)
    known = sheet.existing_keys()
    new_jobs = dedup.filter_known(deduped, known)

    if new_jobs:
        scoring.score_jobs(client, new_jobs, settings)
    to_store = [j for j in new_jobs if j.match_score >= STORE_THRESHOLD]   # drop Low
    counts["_new"] = len(to_store)
    if to_store:
        sheet.append_jobs(to_store)

    unsent = sheet.unsent_rows()
    candidates, row_by_key = [], {}
    for row in unsent:
        job = _row_to_job(row, settings)
        if not _recent(job.posted_ts, settings.recency_days):
            continue
        candidates.append(job)
        if job.dedupe_key:
            row_by_key[job.dedupe_key] = row["_row"]
    takeable, aspirational = _select(candidates, settings)
    selected = takeable + aspirational
    counts["_sent"] = len(selected)

    analysis = _maybe_weekly(sheet, client, settings)

    if not selected and not analysis:
        log.info("Nothing above the send bar and no weekly analysis due — no email.")
        return 0

    html_body = emailer.render_html(takeable, aspirational, analysis, disc.skipped, counts, settings)
    emailer.send(html_body, _subject(settings, len(takeable), len(aspirational), bool(analysis)), settings)

    sent_rows = sorted({row_by_key[j.dedupe_key] for j in selected if j.dedupe_key in row_by_key})
    sheet.mark_sent(sent_rows)
    if analysis:
        sheet.meta_set("last_weekly_analysis", time.strftime("%Y-%m-%d"))

    log.info("Done: found=%d new=%d sent=%d (takeable=%d aspirational=%d)",
             counts["_found"], counts["_new"], counts["_sent"], len(takeable), len(aspirational))
    return len(selected)


def _anthropic_client():
    import anthropic
    return anthropic.Anthropic()


def _maybe_weekly(sheet, client, settings) -> str:
    if client is None:
        return ""
    last = sheet.meta_get("last_weekly_analysis")
    due = True
    if last:
        try:
            last_ts = time.mktime(time.strptime(last, "%Y-%m-%d"))
            due = (time.time() - last_ts) >= settings.weekly_interval_days * 86400
        except ValueError:
            due = True
    if not due:
        return ""
    log.info("Weekly requirements analysis is due — running it.")
    return requirements.analyse(client, sheet.all_jobs(), settings)


def _subject(settings, n_take: int, n_asp: int, weekly: bool) -> str:
    base = f"{settings.digest_title} — {time.strftime('%d %b %Y')} ({n_take} actionable"
    base += f" + {n_asp} aspirational)" if n_asp else ")"
    return base + " + weekly analysis" if weekly else base


def _write_dry(takeable, aspirational, analysis, notes, counts, settings) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"digest_{settings.profile}.html"
    out.write_text(emailer.render_html(takeable, aspirational, analysis, notes, counts, settings))
    log.info("Dry run: wrote %s (no Sheet write, no email)", out)
