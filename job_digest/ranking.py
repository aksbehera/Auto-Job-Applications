"""Ranking + selection — strictly by match score, highest first.

No company-tier or location grouping: fit drives the order, wherever the role
is. (Same-role variants are already collapsed in dedup.dedupe_batch.)
"""

import logging

from .models import Job

log = logging.getLogger(__name__)


def rank(jobs: list[Job]) -> list[Job]:
    """Sort by match score, highest first."""
    return sorted(jobs, key=lambda j: j.match_score, reverse=True)


def select_for_email(jobs: list[Job], cap: int, threshold: int) -> list[Job]:
    """Ranked roles at/above the send threshold, capped."""
    selected = [j for j in rank(jobs) if j.match_score >= threshold][:cap]
    log.info("Selected %d roles for the digest (score >= %d, cap %d)",
             len(selected), threshold, cap)
    return selected
