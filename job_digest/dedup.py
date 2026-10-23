"""De-duplication by company + normalized title + location.

Within a run we collapse the same role seen on multiple platforms (keeping the
best source link); across runs the Google Sheet is the memory — any role whose
key is already stored is dropped so it's never re-added or re-sent.
"""

import hashlib
import logging
import re

from .models import Job

log = logging.getLogger(__name__)

# Preference when the same role appears on several sources — richer JD / direct
# apply first. ATS pages give the cleanest full JD and a direct link.
SOURCE_RANK = {
    "greenhouse": 0, "lever": 0, "ashby": 0,
    "linkedin": 1, "wellfound": 2, "instahyre": 3,
    "naukri": 4, "foundit": 5, "indeed": 6, "glassdoor": 7,
}

_SENIORITY_NOISE = re.compile(
    r"\b(senior|sr|junior|jr|lead|principal|staff|i{1,3}|1|2|3|iv)\b", re.I)

# Geographic tokens used to recognise (and strip) a trailing "- <Location>"
# suffix, so the same role posted per-country collapses to one line.
_GEO = {
    "remote", "hybrid", "onsite", "on", "site",
    "india", "bengaluru", "bangalore", "hyderabad", "gurugram", "gurgaon",
    "delhi", "noida", "ncr", "pune", "mumbai", "chennai", "kolkata", "ahmedabad",
    "us", "usa", "u.s.", "america", "uk", "u.k.", "emea", "apac", "anz", "latam",
    "london", "netherlands", "sweden", "germany", "france", "ireland", "spain",
    "canada", "australia", "singapore", "japan", "korea", "israel", "poland",
    "amsterdam", "berlin", "paris", "dublin", "madrid", "toronto", "sydney",
    "tokyo", "seoul", "telaviv", "warsaw", "munich", "zurich", "europe",
    "york", "new", "san", "francisco", "seattle", "boston", "austin", "chicago",
    "english", "speaking", "based", "region", "global", "worldwide",
    "and", "the", "of", "&",
}


def _strip_geo_suffix(title: str) -> str:
    """Drop a trailing dash/comma segment that is purely a location."""
    for _ in range(3):   # handle "Role - AI Agent - UK - Remote"
        m = re.search(r"\s[-–—,]\s*([^-–—,]+)$", title)
        if not m:
            break
        tail_tokens = re.findall(r"[a-z0-9.]+", m.group(1).lower())
        if tail_tokens and all(tok in _GEO for tok in tail_tokens):
            title = title[: m.start()]
        else:
            break
    return title


def _norm_title(title: str) -> str:
    t = _strip_geo_suffix(title)
    t = t.lower()
    t = re.sub(r"\(.*?\)", " ", t)              # drop parentheticals
    t = _SENIORITY_NOISE.sub(" ", t)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _norm_company(company: str) -> str:
    c = company.lower()
    c = re.sub(r"\b(inc|llc|ltd|pvt|private|limited|corp|corporation|technologies|"
               r"technology|labs|ai|india)\b", " ", c)
    c = re.sub(r"[^a-z0-9 ]", " ", c)
    return re.sub(r"\s+", " ", c).strip()


def _norm_location(location: str) -> str:
    loc = location.lower()
    # Collapse to a coarse bucket: remote, or the first city/region token.
    if re.search(r"remote|anywhere|work from home|wfh", loc):
        return "remote"
    loc = re.sub(r"[^a-z0-9 ]", " ", loc)
    tokens = [t for t in loc.split() if t not in ("india", "in")]
    return tokens[0] if tokens else "na"


def compute_key(job: Job) -> str:
    raw = f"{_norm_company(job.company)}|{_norm_title(job.title)}|{_norm_location(job.location)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def dedupe_batch(jobs: list[Job]) -> list[Job]:
    """Collapse same-role duplicates within this run, keeping the best source."""
    best: dict[str, Job] = {}
    for job in jobs:
        job.dedupe_key = compute_key(job)
        current = best.get(job.dedupe_key)
        if current is None:
            best[job.dedupe_key] = job
            continue
        # Prefer the better source; tie-break on longer JD.
        better = (SOURCE_RANK.get(job.source, 99), -len(job.description))
        incumbent = (SOURCE_RANK.get(current.source, 99), -len(current.description))
        if better < incumbent:
            best[job.dedupe_key] = job
    collapsed = list(best.values())
    log.info("Dedupe (in-run): %d → %d", len(jobs), len(collapsed))
    return collapsed


def filter_known(jobs: list[Job], known_keys: set[str]) -> list[Job]:
    """Drop roles already stored in the Sheet."""
    fresh = [j for j in jobs if j.dedupe_key not in known_keys]
    log.info("Dedupe (vs Sheet): %d new of %d", len(fresh), len(jobs))
    return fresh
