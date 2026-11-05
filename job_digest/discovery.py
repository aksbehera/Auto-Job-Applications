"""Discovery: pull candidate jobs from Apify actors and public ATS career pages.

Every source is fail-soft: if an actor or board errors, it's skipped for this
run and recorded in `DiscoveryResult.skipped` (the emailer footer lists them)
rather than failing the whole run.
"""

import datetime as dt
import html
import logging
import re
import time
from dataclasses import dataclass, field

import requests

from .config import Platform, Settings, env
from .models import Job

log = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2/acts"
APIFY_TIMEOUT_SECS = 300

# Global default field map — merged under each platform's own `fields`.
DEFAULT_FIELDS = {
    "title": ["title", "jobTitle", "positionName", "position", "name", "text"],
    "company": ["companyName", "company", "company_name", "employer", "organization"],
    "location": ["location", "place", "jobLocation", "formattedLocation", "city"],
    "url": ["jobUrl", "url", "link", "applyUrl", "applicationUrl", "hostedUrl",
            "absolute_url", "externalApplyLink"],
    "description": ["description", "descriptionText", "jobDescription", "descriptionHtml",
                    "descriptionPlain", "jobDescriptionText", "content", "text"],
    "posted": ["postedAt", "publishedAt", "postedTime", "postingDateParsed", "postedDate",
               "date", "listedAt", "datePosted", "createdAt", "updated_at"],
    "salary": ["salary", "salaryInfo", "compensation", "salaryText", "payRange"],
    "seniority": ["seniority", "seniorityLevel", "experienceLevel", "level"],
}


@dataclass
class DiscoveryResult:
    jobs: list[Job] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)   # human-readable notes for the footer
    counts: dict = field(default_factory=dict)         # source -> raw count


# ---------------------------------------------------------------- helpers

def _strip_html(raw: str) -> str:
    if not raw:
        return ""
    text = re.sub(r"<\s*br\s*/?>", "\n", raw, flags=re.I)
    text = re.sub(r"</\s*(p|div|li|h[1-6])\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def _scalar(v) -> str:
    """Flatten a value to a string: descend dicts (name/label/…) and lists (first)."""
    if v is None:
        return ""
    if isinstance(v, dict):
        for kk in ("name", "label", "text", "title", "value"):
            if v.get(kk):
                return str(v[kk]).strip()
        return ""
    if isinstance(v, list):
        for item in v:
            s = _scalar(item)
            if s:
                return s
        return ""
    return str(v).strip()


def _first(record: dict, keys: list[str]) -> str:
    for k in keys:
        s = _scalar(record.get(k))
        if s:
            return s
    return ""


def _coerce_ts(v) -> float:
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().isdigit()):
        n = float(v)
        return n / 1000 if n > 1e12 else n
    if isinstance(v, str):
        s = v.strip().replace("Z", "+00:00")
        try:
            return dt.datetime.fromisoformat(s).timestamp()
        except ValueError:
            pass
        # Relative phrasing like "3 days ago", "Posted 5 hours ago".
        m = re.search(r"(\d+)\s*(hour|day|week|month)", s, flags=re.I)
        if m:
            n = int(m.group(1))
            unit = m.group(2).lower()
            mult = {"hour": 3600, "day": 86400, "week": 604800, "month": 2592000}[unit]
            return time.time() - n * mult
        if re.search(r"\b(just now|today|hour|minute)\b", s, flags=re.I):
            return time.time()
        if re.search(r"\byesterday\b", s, flags=re.I):
            return time.time() - 86400
    return 0.0


def _parse_ts(record: dict, keys: list[str]) -> float:
    for k in keys:
        v = record.get(k)
        if not v:
            continue
        if isinstance(v, dict):
            for inner in ("timestamp", "date", "time", "iso", "value"):
                ts = _coerce_ts(v.get(inner))
                if ts:
                    return ts
            continue
        ts = _coerce_ts(v)
        if ts:
            return ts
    return 0.0


def _subst(value, query: str, location: str):
    """Recursively substitute {query}/{location} placeholders in an input template."""
    if isinstance(value, str):
        return value.replace("{query}", query).replace("{location}", location)
    if isinstance(value, list):
        return [_subst(v, query, location) for v in value]
    if isinstance(value, dict):
        return {k: _subst(v, query, location) for k, v in value.items()}
    return value


# ---------------------------------------------------------------- Apify

def run_actor(token: str, actor: str, run_input: dict) -> list[dict]:
    """Run an actor synchronously and return its dataset items."""
    url = f"{APIFY_BASE}/{actor}/run-sync-get-dataset-items"
    resp = requests.post(url, params={"token": token}, json=run_input,
                         timeout=APIFY_TIMEOUT_SECS)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else data.get("items", [])


def _record_to_job(record: dict, platform: Platform) -> Job | None:
    # Some actors nest the job under a sub-object (e.g. Naukri's "jobDetails").
    if platform.root:
        nested = record.get(platform.root)
        if isinstance(nested, dict):
            record = nested
    fields = {k: platform.fields.get(k, []) + DEFAULT_FIELDS[k] for k in DEFAULT_FIELDS}
    title = _first(record, fields["title"])
    company = _first(record, fields["company"])
    url = _first(record, fields["url"])
    if not title or not url:
        return None
    return Job(
        source=platform.name,
        company=company,
        title=title,
        location=_first(record, fields["location"]),
        url=url,
        description=_strip_html(_first(record, fields["description"])),
        posted_ts=_parse_ts(record, fields["posted"]),
        salary=_first(record, fields["salary"]),
        seniority=_first(record, fields["seniority"]),
    )


def discover_apify(settings: Settings, result: DiscoveryResult) -> None:
    token = env("APIFY_TOKEN")
    if not token:
        log.info("APIFY_TOKEN not set — skipping all Apify platforms")
        result.skipped.append("Apify platforms skipped (no APIFY_TOKEN set)")
        return

    for platform in settings.platforms:
        if not platform.enabled:
            continue
        if not platform.actor:
            result.skipped.append(f"{platform.name}: no actor configured")
            continue

        found = 0
        failed_queries = 0
        for query in settings.search_queries:
            run_input = _subst(dict(platform.input), query, settings.default_location)
            try:
                dataset = run_actor(token, platform.actor, run_input)
            except Exception as exc:
                failed_queries += 1
                log.warning("Apify %s / %r failed: %s", platform.name, query, exc)
                continue
            for record in dataset:
                job = _record_to_job(record, platform)
                if job:
                    result.jobs.append(job)
                    found += 1

        result.counts[platform.name] = found
        if failed_queries == len(settings.search_queries) and settings.search_queries:
            result.skipped.append(f"{platform.name}: all queries failed this run")
        log.info("Apify %s: %d raw jobs", platform.name, found)


# ---------------------------------------------------------------- ATS boards

def _greenhouse(company: str, slug: str) -> list[Job]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    jobs = []
    for j in resp.json().get("jobs", []):
        jobs.append(Job(
            source="greenhouse",
            company=company,
            title=j.get("title", ""),
            location=(j.get("location") or {}).get("name", ""),
            url=j.get("absolute_url", ""),
            description=_strip_html(j.get("content", "")),
            posted_ts=_coerce_ts(j.get("updated_at") or j.get("first_published") or ""),
        ))
    return jobs


def _lever(company: str, slug: str) -> list[Job]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    jobs = []
    for j in resp.json():
        cats = j.get("categories", {}) or {}
        desc = j.get("descriptionPlain") or _strip_html(j.get("description", ""))
        jobs.append(Job(
            source="lever",
            company=company,
            title=j.get("text", ""),
            location=cats.get("location", ""),
            url=j.get("hostedUrl", "") or j.get("applyUrl", ""),
            description=desc,
            posted_ts=_coerce_ts(j.get("createdAt") or ""),
            salary=(j.get("salaryRange") or {}).get("currency", "") if j.get("salaryRange") else "",
        ))
    return jobs


def _ashby(company: str, slug: str) -> list[Job]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    jobs = []
    for j in resp.json().get("jobs", []):
        comp = j.get("compensation") or {}
        summary = comp.get("compensationTierSummary", "") if isinstance(comp, dict) else ""
        jobs.append(Job(
            source="ashby",
            company=company,
            title=j.get("title", ""),
            location=j.get("location", "") or j.get("locationName", ""),
            url=j.get("jobUrl", "") or j.get("applyUrl", ""),
            description=j.get("descriptionPlain") or _strip_html(j.get("descriptionHtml", "")),
            posted_ts=_coerce_ts(j.get("publishedAt") or j.get("updatedAt") or ""),
            salary=summary,
        ))
    return jobs


_ATS_FETCHERS = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby}


def discover_ats(settings: Settings, result: DiscoveryResult) -> None:
    for provider, boards in settings.ats_boards.items():
        fetch = _ATS_FETCHERS.get(provider)
        if not fetch:
            result.skipped.append(f"ATS provider '{provider}' not supported")
            continue
        found = 0
        for board in boards:
            company, slug = board.get("company", ""), board.get("slug", "")
            if not slug:
                continue
            try:
                jobs = fetch(company, slug)
            except Exception as exc:
                log.warning("ATS %s/%s (%s) failed: %s", provider, slug, company, exc)
                result.skipped.append(f"{provider}:{company} board unreachable")
                continue
            result.jobs.extend(jobs)
            found += len(jobs)
        result.counts[f"ats:{provider}"] = found
        log.info("ATS %s: %d raw jobs", provider, found)


# ---------------------------------------------------------------- entry point

def discover(settings: Settings, use_apify: bool = True, use_ats: bool = True) -> DiscoveryResult:
    result = DiscoveryResult()
    if use_ats:
        discover_ats(settings, result)
    if use_apify:
        discover_apify(settings, result)
    log.info("Discovery: %d raw jobs total", len(result.jobs))
    return result
