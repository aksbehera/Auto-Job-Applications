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


def assign_group(job: Job, settings: Settings) -> str:
    """Location-first grouping that honours the brief's priority order.

      target        — a target company AND India- or remote-eligible (take it)
      remote        — remote / India-eligible, non-target
      india         — India on-site/hybrid, non-target
      opportunistic — target company but international on-site (lowest priority)
      ""            — international on-site, non-target → dropped

    A target company abroad no longer outranks a real India/remote AI-PM role.
    """
    india = _is_india(job, settings)
    if job.tier and (india or job.remote):
        return "target"
    if job.remote:
        return "remote"
    if india:
        return "india"
    if job.tier:
        return "opportunistic"
    return ""


def _score(job: Job, settings: Settings) -> float:
    s = _title_closeness(job.title, settings)          # 0..1 title fit
    t = _norm(job.title)
    # Prefer true Product Manager roles (the core lane) over solutions-only.
    if _has(t, settings.pm_terms):
        s += 0.30
    elif _has(t, settings.solutions_terms):
        s += 0.10
    # Location is the dominant lever: India/remote up, international on-site down.
    if job.remote or _is_india(job, settings):
        s += 0.40
    else:
        s -= 0.15
    s += {"strong-fit": 0.25, "reach": 0.15, "safe": 0.10}.get(job.tier, 0.0)
    return round(s, 4)


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

        # Solutions-engineer roles that are really DSA/code-gated SWE → drop
        # unless they're at a target company (keep those, flagged in summary).
        if _code_gated(job, settings) and not tier \
                and any(t in _norm(job.title) for t in settings.solutions_terms):
            dropped["code_gate"] += 1
            continue

        # Location-first grouping (see assign_group). An international on-site,
        # non-target role returns "" and is dropped.
        job.group = assign_group(job, settings)
        if not job.group:
            dropped["location"] += 1
            continue

        job.score = _score(job, settings)
        kept.append(job)

    log.info("Classify: kept %d; dropped lane=%d junior=%d code_gate=%d location=%d",
             len(kept), dropped["lane"], dropped["junior"],
             dropped["code_gate"], dropped["location"])
    return kept
