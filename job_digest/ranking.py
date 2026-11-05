"""Ranking + digest selection.

Grouping, per the brief:
  1. Target-company roles (any tier) — surfaced first
  2. Remote (India-eligible / global-remote)
  3. India on-site / hybrid

Within each group, order by match score (desc). The overall digest is capped,
filling group 1, then 2, then 3, so target-company + strong-title roles lead.
"""

import logging

from .dedup import _norm_company, _norm_title
from .models import Job

log = logging.getLogger(__name__)

GROUP_ORDER = ["target", "remote", "india", "opportunistic"]
GROUP_LABELS = {
    "target": "Target-company roles (India / remote)",
    "remote": "Remote (India-eligible / global-remote)",
    "india": "India on-site / hybrid",
    "opportunistic": "Opportunistic — target companies, international",
}

# No single company may take more than this many slots in one digest.
PER_COMPANY_CAP = 3


def group_jobs(jobs: list[Job]) -> dict[str, list[Job]]:
    groups: dict[str, list[Job]] = {g: [] for g in GROUP_ORDER}
    for job in jobs:
        groups.get(job.group, groups["india"]).append(job)
    for g in groups:
        groups[g].sort(key=lambda j: j.score, reverse=True)
    return groups


def collapse_variants(jobs: list[Job]) -> list[Job]:
    """Collapse the same company+title across locations into one representative.

    The highest-scoring posting represents the role; its `variant_keys` carry
    every collapsed posting's dedupe key so the pipeline can mark them all sent.
    All postings remain stored individually in the Sheet.
    """
    groups: dict[tuple[str, str], list[Job]] = {}
    for job in jobs:
        groups.setdefault((_norm_company(job.company), _norm_title(job.title)), []).append(job)
    reps: list[Job] = []
    for members in groups.values():
        members.sort(key=lambda j: j.score, reverse=True)
        rep = members[0]
        rep.variant_count = len(members)
        rep.variant_keys = [m.dedupe_key for m in members if m.dedupe_key]
        reps.append(rep)
    return reps


def select_for_digest(jobs: list[Job], cap: int) -> list[Job]:
    """Pick up to `cap` distinct roles, prioritising target → remote → india →
    opportunistic, with no single company taking more than PER_COMPANY_CAP slots
    so one employer's bulk postings can't flood the digest."""
    reps = collapse_variants(jobs)
    groups = group_jobs(reps)
    selected: list[Job] = []
    per_company: dict[str, int] = {}
    for g in GROUP_ORDER:
        for job in groups[g]:
            if len(selected) >= cap:
                break
            c = _norm_company(job.company)
            if per_company.get(c, 0) >= PER_COMPANY_CAP:
                continue
            per_company[c] = per_company.get(c, 0) + 1
            selected.append(job)
    log.info("Selected %d distinct roles (from %d postings, %d candidate roles)",
             len(selected), len(jobs), len(reps))
    return selected
