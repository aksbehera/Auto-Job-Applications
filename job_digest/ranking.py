"""Ranking + selection — strictly by match score, highest first.

The digest has two parts: the actionable shortlist (takeable from India, score at
or above the send bar) and, parked separately, the aspirational international
roles (not takeable now, but strong on paper). (Same-role variants are already
collapsed in dedup.dedupe_batch.)
"""

import logging

from .models import Job

log = logging.getLogger(__name__)


def rank(jobs: list[Job]) -> list[Job]:
    """Sort by match score, highest first."""
    return sorted(jobs, key=lambda j: j.match_score, reverse=True)


def select_takeable(jobs: list[Job], cap: int, threshold: int) -> list[Job]:
    """Takeable roles at/above the send threshold, ranked by score."""
    out = [j for j in rank(jobs) if j.takeable and j.match_score >= threshold][:cap]
    log.info("Takeable shortlist: %d roles (score >= %d, cap %d)", len(out), threshold, cap)
    return out


def select_aspirational(jobs: list[Job], cap: int, raw_threshold: int) -> list[Job]:
    """Not-takeable roles that are strong on paper, ranked by uncapped fit."""
    pool = [j for j in jobs if not j.takeable and j.raw_score >= raw_threshold]
    pool.sort(key=lambda j: j.raw_score, reverse=True)
    out = pool[:cap]
    log.info("Aspirational (relocation+visa) section: %d roles (raw >= %d)", len(out), raw_threshold)
    return out
