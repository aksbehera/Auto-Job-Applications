"""De-duplication by company + normalized title (location-independent).

Collapsing is location-free on purpose: the same role posted across several
cities is one opportunity, and a location-free identity means the Google Sheet's
memory recognises it next run even if only a different city's posting shows up —
so a role is never re-scored, re-stored, or re-sent.
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

# Geographic tokens used to strip a trailing "- <Location>" suffix so the same
# role posted per-city/country collapses to one identity.
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
    for _ in range(3):
        m = re.search(r"\s[-–—,]\s*([^-–—,]+)$", title)
        if not m:
            break
        tail = re.findall(r"[a-z0-9.]+", m.group(1).lower())
        if tail and all(tok in _GEO for tok in tail):
            title = title[: m.start()]
        else:
            break
    return title


def _norm_title(title: str) -> str:
    t = _strip_geo_suffix(title).lower()
    t = re.sub(r"\(.*?\)", " ", t)
    t = _SENIORITY_NOISE.sub(" ", t)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _norm_company(company: str) -> str:
    c = company.lower()
    c = re.sub(r"\b(inc|llc|ltd|pvt|private|limited|corp|corporation|technologies|"
               r"technology|labs|ai|india)\b", " ", c)
    c = re.sub(r"[^a-z0-9 ]", " ", c)
    return re.sub(r"\s+", " ", c).strip()


def compute_key(job: Job) -> str:
    raw = f"{_norm_company(job.company)}|{_norm_title(job.title)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def dedupe_batch(jobs: list[Job]) -> list[Job]:
    """Collapse same-role duplicates (across platforms and locations) to one
    representative — best source, longest JD — recording how many merged."""
    best: dict[str, Job] = {}
    for job in jobs:
        job.dedupe_key = compute_key(job)
        cur = best.get(job.dedupe_key)
        if cur is None:
            job.variant_count = 1
            best[job.dedupe_key] = job
            continue
        cur.variant_count += 1
        rank_new = (SOURCE_RANK.get(job.source, 99), -len(job.description))
        rank_cur = (SOURCE_RANK.get(cur.source, 99), -len(cur.description))
        if rank_new < rank_cur:
            job.variant_count = cur.variant_count
            best[job.dedupe_key] = job
    collapsed = list(best.values())
    log.info("Dedupe: %d postings → %d distinct roles", len(jobs), len(collapsed))
    return collapsed


def filter_known(jobs: list[Job], known_keys: set[str]) -> list[Job]:
    fresh = [j for j in jobs if j.dedupe_key not in known_keys]
    log.info("Dedupe (vs Sheet): %d new of %d", len(fresh), len(jobs))
    return fresh
