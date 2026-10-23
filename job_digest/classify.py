"""Rule-based classification: lane match, exclusions, tier, location, scoring.

This is deliberately deterministic (no LLM) so filtering is cheap and
predictable. The LLM is used only later, for summaries and the weekly analysis.
"""

import logging
import re

from .config import Settings
from .models import Job

log = logging.getLogger(__name__)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _has(text: str, terms: list[str]) -> bool:
    return any(t in text for t in terms)


def _company_tier(company: str, settings: Settings) -> str:
    c = _norm(company)
    if not c:
        return ""
    for tier, names in settings.companies.items():
        for name in names:
            n = _norm(name)
            # Match on a word-ish boundary so "Clari" doesn't hit "Declarative".
            if n and (c == n or re.search(rf"(^|[^a-z0-9]){re.escape(n)}([^a-z0-9]|$)", c)):
                return tier
    return ""


def _title_in_lane(title: str, settings: Settings) -> tuple[bool, bool]:
    """Return (in_lane, is_excluded_but_rescued).

    A title is in the lane if it carries a product OR solutions signal AND an
    AI signal. Excluded terms drop it unless a strong product/solutions signal
    is also present (e.g. "AI Product Manager, Data Science Platform").
    """
    t = _norm(title)
    has_pm = _has(t, settings.pm_terms)
    has_se = _has(t, settings.solutions_terms)
    has_ai = _has(t, settings.ai_terms)
    role_signal = has_pm or has_se

    excluded = _has(t, settings.exclude_titles)
    if excluded and not role_signal:
        return False, False

    in_lane = role_signal and has_ai
    return in_lane, (excluded and role_signal)


def _is_remote(job: Job, settings: Settings) -> bool:
    blob = _norm(f"{job.location} {job.title} {job.description[:600]}")
    return _has(blob, settings.remote_terms)


def _is_india(job: Job, settings: Settings) -> bool:
    return _has(_norm(f"{job.location} {job.description[:400]}"), settings.india_terms)


def _seniority(job: Job, settings: Settings) -> tuple[str, bool]:
    """Return (label, is_junior). Junior roles are filtered out."""
    t = _norm(f"{job.title} {job.seniority}")
    if _has(t, settings.junior_terms):
        return ("Junior", True)
    for term in ("principal", "director", "vp", "vice president", "head",
                 "lead", "staff", "senior", "sr", "manager", "group"):
        if re.search(rf"(^|[^a-z]){re.escape(term)}([^a-z]|$)", t):
            return (term.title(), False)
    return ("Mid", False)


def _code_gated(job: Job, settings: Settings) -> bool:
    return _has(_norm(job.description), settings.code_gate_terms)


def _title_closeness(title: str, settings: Settings) -> float:
    """0..1 token-overlap against the closest target title exemplar."""
    t = set(re.findall(r"[a-z0-9]+", _norm(title)))
    if not t:
        return 0.0
    best = 0.0
    for exemplar in settings.target_titles:
        e = set(re.findall(r"[a-z0-9]+", _norm(exemplar)))
        if not e:
            continue
        best = max(best, len(t & e) / len(e))
    return min(best, 1.0)


def _score(job: Job, settings: Settings) -> float:
    s = _title_closeness(job.title, settings)          # 0..1 title fit
    tier_bonus = {"strong-fit": 0.6, "reach": 0.4, "safe": 0.25}.get(job.tier, 0.0)
    # Location nudge: remote (India-eligible) ranks above India on-site.
    if job.remote:
        loc_bonus = 0.25
    elif _is_india(job, settings):
        loc_bonus = 0.15
    else:
        loc_bonus = 0.0
    return round(s + tier_bonus + loc_bonus, 4)


def classify(jobs: list[Job], settings: Settings) -> list[Job]:
    """Filter to the lane and annotate tier / remote / group / seniority / score."""
    kept: list[Job] = []
    dropped = {"lane": 0, "junior": 0, "code_gate": 0, "location": 0}

    for job in jobs:
        in_lane, _ = _title_in_lane(job.title, settings)
        if not in_lane:
            dropped["lane"] += 1
            continue

        label, is_junior = _seniority(job, settings)
        if is_junior:
            dropped["junior"] += 1
            continue
        job.seniority = label

        tier = _company_tier(job.company, settings)
        job.tier = tier
        job.remote = _is_remote(job, settings)
        is_india = _is_india(job, settings)

        # Solutions-engineer roles that are really DSA/code-gated SWE → drop
        # unless they're at a target company (keep those, flagged in summary).
        if _code_gated(job, settings) and not tier \
                and any(t in _norm(job.title) for t in settings.solutions_terms):
            dropped["code_gate"] += 1
            continue

        # Location gate:
        #   target company        → always keep (opportunistic international ok)
        #   remote                 → keep (group: remote)
        #   India on-site/hybrid   → keep (group: india)
        #   international on-site, non-target, non-remote → drop
        if tier:
            job.group = "target"
        elif job.remote:
            job.group = "remote"
        elif is_india:
            job.group = "india"
        else:
            dropped["location"] += 1
            continue

        job.score = _score(job, settings)
        kept.append(job)

    log.info("Classify: kept %d; dropped lane=%d junior=%d code_gate=%d location=%d",
             len(kept), dropped["lane"], dropped["junior"],
             dropped["code_gate"], dropped["location"])
    return kept
