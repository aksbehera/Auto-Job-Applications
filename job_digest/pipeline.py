"""End-to-end pipeline:

  discover → classify (lane) → recency → dedupe (in-run) → dedupe (vs Sheet)
  → summarise new roles → store in Sheet → select digest from unsent rows
  → (weekly) requirements analysis → email → mark sent.

The Google Sheet is the system of record and the dedupe memory, so a role is
never stored twice and never emailed twice.
"""

import logging
import time

from . import classify, dedup, discovery, emailer, ranking, requirements, summarize
from .config import OUT_DIR, load_settings
from .models import Job

log = logging.getLogger(__name__)


def _recent(ts: float, recency_days: int) -> bool:
    """Keep unknown-date roles; drop only those known to be too old."""
    return not (ts and (time.time() - ts) > recency_days * 86400)


def _row_to_job(row: dict) -> Job:
    posted = str(row.get("Posted date", "")).strip()
    posted_ts = 0.0
    if posted:
        try:
            posted_ts = time.mktime(time.strptime(posted, "%Y-%m-%d"))
        except ValueError:
            posted_ts = 0.0
    try:
        score = float(row.get("Match score", 0) or 0)
    except ValueError:
        score = 0.0
    tier = str(row.get("Tier", "")).strip()
    tier = "" if tier in ("", "—") else tier
    remote = str(row.get("Remote?", "")).strip().lower() == "yes"
    job = Job(
        source=str(row.get("Source platform", "")),
        company=str(row.get("Company", "")),
        title=str(row.get("Title", "")),
        location=str(row.get("Location", "")),
        url=str(row.get("Apply URL", "")),
        description=str(row.get("Full JD", "")),
        posted_ts=posted_ts,
        salary=str(row.get("Salary/comp", "")),
        seniority=str(row.get("Seniority", "")),
        remote=remote,
        tier=tier,
        score=score,
        summary=str(row.get("Short summary", "")),
        dedupe_key=str(row.get("Dedupe key", "")),
    )
    job.group = "target" if tier else ("remote" if remote else "india")
    job.requirements = [r.strip() for r in str(row.get("Key requirements/skills", "")).split(";")
                        if r.strip()]
    return job


def run(dry_run: bool = False, use_apify: bool = True, use_ats: bool = True,
        use_llm: bool = True) -> int:
    settings = load_settings()

    # 1. Discover
    disc = discovery.discover(settings, use_apify=use_apify, use_ats=use_ats)
    counts = dict(disc.counts)
    counts["_found"] = len(disc.jobs)

    # 2. Classify to the lane, 3. recency, 4. in-run dedupe
    laned = classify.classify(disc.jobs, settings)
    laned = [j for j in laned if _recent(j.posted_ts, settings.recency_days)]
    deduped = dedup.dedupe_batch(laned)

    client = _anthropic_client() if use_llm else None

    if dry_run:
        # No Sheet, no creds needed: summarise + render just this run's finds.
        if client:
            summarize.summarize_jobs(client, deduped)
        else:
            for j in deduped:
                summarize._fallback(j)
        counts["_new"] = len(deduped)
        selected = ranking.select_for_digest(deduped, settings.max_items_per_digest)
        counts["_sent"] = len(selected)
        _write_dry(selected, "", disc.skipped, counts)
        return len(selected)

    # 5. Dedupe vs the Sheet (the memory), 6. summarise only genuinely new roles
    from .sheet import JobSheet
    sheet = JobSheet()
    known = sheet.existing_keys()
    new_jobs = dedup.filter_known(deduped, known)
    counts["_new"] = len(new_jobs)

    if new_jobs:
        if client:
            summarize.summarize_jobs(client, new_jobs)
        else:
            for j in new_jobs:
                summarize._fallback(j)
        sheet.append_jobs(new_jobs)

    # 7. Build the digest from ALL unsent rows (new + any leftovers), ranked/capped.
    unsent = sheet.unsent_rows()
    candidates, row_by_key = [], {}
    for row in unsent:
        job = _row_to_job(row)
        if not _recent(job.posted_ts, settings.recency_days):
            continue
        candidates.append(job)
        if job.dedupe_key:
            row_by_key[job.dedupe_key] = row["_row"]
    selected = ranking.select_for_digest(candidates, settings.max_items_per_digest)
    counts["_sent"] = len(selected)

    # 8. Weekly requirements analysis (cadence tracked in the Sheet _meta tab)
    analysis = _maybe_weekly(sheet, client, settings)

    if not selected and not analysis:
        log.info("Nothing new to send and no weekly analysis due — no email.")
        return 0

    html_body = emailer.render_html(selected, analysis, disc.skipped, counts)
    subject = _subject(len(selected), bool(analysis))
    emailer.send(html_body, subject)

    # 9. Mark the selected rows — and every collapsed location-variant — as sent,
    #    so the same role never resurfaces in a later digest.
    sent_rows = []
    for job in selected:
        for key in (job.variant_keys or [job.dedupe_key]):
            if key in row_by_key:
                sent_rows.append(row_by_key[key])
    sheet.mark_sent(sorted(set(sent_rows)))
    if analysis:
        sheet.meta_set("last_weekly_analysis", time.strftime("%Y-%m-%d"))

    log.info("Done: found=%d new=%d sent=%d", counts["_found"], counts["_new"], counts["_sent"])
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
    return requirements.analyse(client, sheet.all_jobs())


def _subject(n: int, weekly: bool) -> str:
    base = f"AI PM Job Digest — {time.strftime('%d %b %Y')} ({n} role{'s' if n != 1 else ''})"
    return base + " + weekly analysis" if weekly else base


def _write_dry(selected, analysis, notes, counts) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    html_body = emailer.render_html(selected, analysis, notes, counts)
    out_path = OUT_DIR / "digest.html"
    out_path.write_text(html_body)
    log.info("Dry run: wrote %s (no Sheet write, no email)", out_path)
