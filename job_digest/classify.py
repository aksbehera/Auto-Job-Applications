"""Cheap pre-filter + metadata, run before the LLM scorer.

This is deliberately permissive and keyword-based: its only job is to cut ~3,000
raw postings down to a bounded candidate set worth spending an LLM call on, and
to attach metadata (company tier, remote flag, seniority) the scorer uses. The
real fit judgement and exclusions happen in scoring.py, which reads each JD —
so this never drops a role for a title reason the scorer should decide.
"""

import logging
import re

from .config import Settings
from .models import Job

log = logging.getLogger(__name__)

# Strong AI signals in a JD body — lets a plainly-titled "Product Manager" at an
# AI-native company through to scoring without admitting every generic PM role.
STRONG_AI_DESC = ("genai", "generative ai", "llm", "large language model",
                  "agentic", "rag", "ai agent", "ai product")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _has(text: str, terms) -> bool:
    return any(t in text for t in terms)


def _company_tier(company: str, settings: Settings) -> str:
    c = _norm(company)
    if not c:
        return ""
    for tier, names in settings.companies.items():
        for name in names:
            n = _norm(name)
            if n and (c == n or re.search(rf"(^|[^a-z0-9]){re.escape(n)}([^a-z0-9]|$)", c)):
                return tier
    return ""


def _is_remote(job: Job, settings: Settings) -> bool:
    return _has(_norm(f"{job.location} {job.title} {job.description[:600]}"), settings.remote_terms)


def _is_india(job: Job, settings: Settings) -> bool:
    return _has(_norm(f"{job.location} {job.description[:400]}"), settings.india_terms)


def _seniority(job: Job, settings: Settings) -> tuple[str, bool]:
    t = _norm(f"{job.title} {job.seniority}")
    if _has(t, settings.junior_terms):
        return ("Junior", True)
    for term in ("principal", "director", "vp", "vice president", "head",
                 "lead", "staff", "senior", "sr", "manager", "group"):
        if re.search(rf"(^|[^a-z]){re.escape(term)}([^a-z]|$)", t):
            return (term.title(), False)
    return ("Mid", False)


def _in_lane(job: Job, settings: Settings) -> bool:
    """Title carries a role signal (product/solutions, or sales/BD for other
    profiles). When the profile requires a domain signal (e.g. AI PM), also
    require it in the title, via a target company, or strongly in the JD body."""
    title = _norm(job.title)
    role_signal = _has(title, settings.pm_terms) or _has(title, settings.solutions_terms)
    if not role_signal:
        return False
    if not settings.require_domain_signal:
        return True
    if _has(title, settings.ai_terms):
        return True
    if _company_tier(job.company, settings):
        return True
    return _has(_norm(job.description[:1500]), STRONG_AI_DESC)


def classify(jobs: list[Job], settings: Settings) -> list[Job]:
    """Keep plausible candidates and tag tier / remote / seniority for scoring."""
    kept: list[Job] = []
    dropped = {"lane": 0, "junior": 0}
    for job in jobs:
        if not _in_lane(job, settings):
            dropped["lane"] += 1
            continue
        label, is_junior = _seniority(job, settings)
        if is_junior:
            dropped["junior"] += 1
            continue
        job.seniority = label
        job.tier = _company_tier(job.company, settings)
        job.remote = _is_remote(job, settings)
        kept.append(job)
    log.info("Classify (pre-filter): kept %d; dropped lane=%d junior=%d",
             len(kept), dropped["lane"], dropped["junior"])
    return kept
