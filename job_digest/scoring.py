"""LLM match-scoring: a 0–100 fit score on every role, read from the full JD.

One call per role returns the role summary, parsed requirements, six weighted
sub-scores, a one-line rationale, the biggest fit reason and gap/risk, and three
judgements: whether the role is TAKEABLE from India now, whether a hard must-have
is unmet, and whether the role is actually code-gated engineering. Code computes
the weighted total, applies the hard caps, and sets the band.

Takeability is decisive (v2): a role the candidate physically cannot take from
India — international on-site, US-state-locked, or US-only "remote" with no stated
India hiring/visa sponsorship — is capped so it can never read as Strong, no
matter how good the company or the fit. Company quality does not change
takeability.
"""

import json
import logging
import re

from .classify import _is_india
from .config import BANDS, SUMMARY_MODEL, load_profile
from .models import Job

log = logging.getLogger(__name__)

# Dimension weights (sum to 100). Sub-scores are 0–1; raw score = Σ weight·sub.
WEIGHTS = {
    "role_type": 30,
    "domain": 20,
    "seniority": 15,
    "company": 15,
    "location": 15,
    "feasibility": 5,
}
NOT_TAKEABLE_CAP = 60   # a role he can't take from India can't read as Strong
JD_CHARS = 12000        # score on the full JD, not a snippet
PARTIAL_JD_CHARS = 400  # below this the JD is treated as partial → provisional

# The scoring system prompt and the per-dimension rubric are profile-specific and
# come from settings (profiles/<name>/targets.yaml + rubric.md), so the same
# engine scores an AI-PM search and a sales search by different criteria.

_PROMPT = """CANDIDATE PROFILE
{profile}

{rubric}

ROLE
Title: {title}
Company: {company}  (target-list tier hint: {tier})
Location: {location}   remote_flag={remote}   india_flag={india}   seniority_hint={seniority}

JOB DESCRIPTION
\"\"\"
{jd}
\"\"\"

Return ONLY this JSON object:
{{
  "summary": "2-3 sentences: what the role is + its single most important requirement",
  "requirements": ["4-8 short strings: key required skills/tools/experience"],
  "subscores": {{"role_type":0-1,"domain":0-1,"seniority":0-1,"company":0-1,"location":0-1,"feasibility":0-1}},
  "rationale": "one line: why this score",
  "fit_reason": "the single biggest reason this fits him",
  "gap_risk": "the single biggest gap or risk",
  "takeable": true/false,
  "excluded_role_type": true/false,
  "unmet_must_have": true/false,
  "partial_jd": true/false,
  "blocker": "the unmet must-have, or empty"
}}

Write compact JSON. Inside any string value do not use the double-quote
character (use single quotes if you must) and do not use line breaks."""


def _band(score: int) -> str:
    for cutoff, name in BANDS:
        if score >= cutoff:
            return name
    return "Low"


def _weighted(sub: dict, weights: dict) -> int:
    total = sum(weights[d] * max(0.0, min(1.0, float(sub.get(d, 0) or 0))) for d in WEIGHTS)
    return int(round(total))


def _parse_json(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S).strip()
    t = t[t.find("{"): t.rfind("}") + 1]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        return json.loads(re.sub(r'(?<!\\)[\n\r\t]+', " ", t))


def _apply_gates(job: Job, data: dict, weights: dict) -> int:
    """Raw weighted score, then hard caps; sets job.raw_score and exclude tags."""
    raw = _weighted(job.subscores, weights)
    job.raw_score = raw
    score = raw
    if not data.get("takeable", True):
        job.takeable = False
        score = min(score, NOT_TAKEABLE_CAP)
        job.exclude_tag = "relocation + visa required"
    if data.get("unmet_must_have"):
        score = min(score, 30)
        blk = str(data.get("blocker", "")).strip()
        job.exclude_tag = ("unmet-must-have" + (f": {blk}" if blk else "")) if not job.exclude_tag \
            else job.exclude_tag
    if data.get("excluded_role_type"):
        score = min(score, 15)
        job.exclude_tag = "excluded-role-type"
    return max(0, min(100, score))


def _fallback(job: Job, settings, weights: dict) -> None:
    india = _is_india(job, settings)
    job.takeable = bool(job.remote or india)
    sub = {
        "role_type": 0.5, "domain": 0.5,
        "seniority": 0.0 if job.seniority == "Junior" else 0.7,
        "company": {"strong-fit": 1.0, "reach": 0.8, "safe": 0.5}.get(job.tier, 0.4),
        "location": 1.0 if (job.remote and india) else (0.9 if india else (0.5 if job.remote else 0.1)),
        "feasibility": 1.0,
    }
    job.subscores = sub
    job.raw_score = _weighted(sub, weights)
    job.match_score = min(job.raw_score, NOT_TAKEABLE_CAP) if not job.takeable else job.raw_score
    job.band = _band(job.match_score)
    job.provisional = len((job.description or "").strip()) < PARTIAL_JD_CHARS
    job.rationale = "Heuristic fallback (LLM scoring unavailable)."
    job.summary = (" ".join(job.description.split())[:280] if job.description.strip()
                   else f"{job.title} at {job.company}. Full JD not provided by source.")


def _score_call(client, prompt: str, system: str) -> dict:
    resp = client.messages.create(
        model=SUMMARY_MODEL, max_tokens=800, system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        return _parse_json(resp.content[0].text)
    except (json.JSONDecodeError, ValueError):
        resp = client.messages.create(
            model=SUMMARY_MODEL, max_tokens=800, system=system,
            messages=[
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": resp.content[0].text},
                {"role": "user", "content": "That was not valid JSON. Return ONLY a valid, "
                 "compact JSON object with the same keys, every inner double-quote escaped "
                 "as \\\" and no line breaks inside strings."},
            ],
        )
        return _parse_json(resp.content[0].text)


def score_jobs(client, jobs: list[Job], settings) -> None:
    profile = load_profile(settings.profile) or "(no profile provided)"
    system = settings.scoring_system or "You score job fit for a candidate. Return only JSON."
    rubric = settings.scoring_rubric
    weights = settings.weights
    for job in jobs:
        if client is None:
            _fallback(job, settings, weights)
            continue
        prompt = _PROMPT.format(
            profile=profile, rubric=rubric,
            title=job.title, company=job.company, tier=job.tier or "not listed",
            location=job.location or "(unspecified)", remote=job.remote,
            india=_is_india(job, settings), seniority=job.seniority or "(unknown)",
            jd=(job.description or job.title)[:JD_CHARS],
        )
        try:
            data = _score_call(client, prompt, system)
            job.summary = str(data.get("summary", "")).strip()
            job.requirements = [str(r).strip() for r in data.get("requirements", []) if str(r).strip()][:8]
            job.subscores = {d: float(data.get("subscores", {}).get(d, 0) or 0) for d in WEIGHTS}
            job.rationale = str(data.get("rationale", "")).strip()
            job.fit_reason = str(data.get("fit_reason", "")).strip()
            job.gap_risk = str(data.get("gap_risk", "")).strip()
            job.takeable = bool(data.get("takeable", True))
            job.match_score = _apply_gates(job, data, weights)
            job.band = _band(job.match_score)
            job.provisional = bool(data.get("partial_jd")) or \
                len((job.description or "").strip()) < PARTIAL_JD_CHARS
            if not job.summary:
                job.summary = f"{job.title} at {job.company}."
        except Exception as exc:
            log.warning("Scoring failed for %r @ %s: %s", job.title, job.company, exc)
            _fallback(job, settings, weights)
