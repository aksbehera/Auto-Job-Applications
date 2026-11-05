"""LLM match-scoring: a 0–100 fit score on every role, read from the JD.

One call per role returns the role summary, parsed requirements, six weighted
sub-scores, a one-line rationale, the biggest fit reason and the biggest
gap/risk, plus gate flags. Code computes the weighted total and applies the
hard caps, so exclusions (code-gated / ML-eng / data-architect, international
on-site with no India path, unmet must-haves) are decided by the JD, not the
title.
"""

import json
import logging
import re

from .classify import _is_india
from .config import BANDS, SUMMARY_MODEL, load_profile
from .models import Job

log = logging.getLogger(__name__)

# Dimension weights (sum to 100). Sub-scores are 0–1; score = Σ weight·sub.
WEIGHTS = {
    "role_type": 30,
    "domain": 20,
    "seniority": 15,
    "company": 15,
    "location": 15,
    "feasibility": 5,
}

_SYSTEM = (
    "You are a sharp technical recruiter scoring AI / product roles for one "
    "specific candidate. Judge TRUE fit by reading the job description's must-have "
    "requirements, never by the title alone — a role can carry a target-lane title "
    "and still be a hard misfit. Be decisive and honest. Return only JSON."
)

_RUBRIC = """Score each dimension from 0.0 to 1.0:

role_type — is this the right KIND of role?
  1.0 core AI/GenAI Product Manager; 0.7 adjacent product (AI Product Owner,
  Applied-AI PM, product-builder); 0.4 consultative/customer-facing solutions
  (solutions engineer / forward-deployed / solutions architect that is discovery,
  scoping, demos, solutioning, delivery — NOT writing production code or training
  models); 0.0 code-gated engineering, ML/AI engineer (training, fine-tuning,
  SFT/RLHF, MLOps), data/solution architect as the core job, IC data/research
  scientist, or non-AI/generic PM, product marketing, program/project manager.

domain — agentic AI, LLMs, RAG, agents, GenAI, enterprise AI at the core.
  1.0 agentic/LLM product at the core; partial for adjacent; small bonus if it
  rewards decision-science/experimentation/ML-product-sense or media-generation.

seniority — level vs ~11 years / manager.
  1.0 manager/senior/lead/staff at ~8–15 yrs; 0.5 slightly off (PM II, or 15+ yrs
  required); 0.1 clearly junior or VP/Director-only.

company — 1.0 strong-fit target; 0.8 reach target; 0.7 strong non-listed
  AI-native; 0.5 safe/listed; 0.3 ordinary/unknown. (Tier hint is provided, but
  judge AI-nativeness from the JD too.)

location — 1.0 remote India-eligible; 0.9 India on-site/hybrid; 0.5 international
  remote that is plausibly India-eligible; 0.1 international on-site or
  US-state-locked (e.g. "must reside in Colorado").

feasibility — 1.0 no blockers; lower for visa-required international with no stated
  India hiring/sponsorship, immediate/0–15-day-joiner demands, or a hard must-have
  the candidate lacks (he does NOT hand-write production code or train models).

Also set these gate flags (booleans):
  excluded_role_type  — true if role_type is 0 (code-gated eng / ML-eng /
                        data-architect / IC DS / non-AI or generic PM).
  intl_onsite_no_india — true if the role is international on-site / US-state-locked
                        with no India path.
  unmet_must_have     — true if a stated hard must-have is something he lacks
                        (e.g. "must have hands-on fine-tuning", "must code in
                        production"); put that requirement in "blocker"."""

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
  "excluded_role_type": true/false,
  "intl_onsite_no_india": true/false,
  "unmet_must_have": true/false,
  "blocker": "the unmet must-have, or empty"
}}

Write compact JSON. Inside any string value do not use the double-quote
character (use single quotes if you must) and do not use line breaks."""


def _parse_json(text: str) -> dict:
    """Parse the model's JSON tolerantly: strip code fences, isolate the object,
    and if it still fails, escape raw newlines inside string values and retry."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S).strip()
    t = t[t.find("{"): t.rfind("}") + 1]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        # Replace literal newlines/tabs that appear inside quoted strings.
        repaired = re.sub(r'(?<!\\)[\n\r\t]+', " ", t)
        return json.loads(repaired)


def _band(score: int) -> str:
    for cutoff, name in BANDS:
        if score >= cutoff:
            return name
    return "Low"


def _weighted(sub: dict) -> int:
    total = sum(WEIGHTS[d] * max(0.0, min(1.0, float(sub.get(d, 0) or 0))) for d in WEIGHTS)
    return int(round(total))


def _apply_gates(job: Job, data: dict, settings) -> int:
    score = _weighted(job.subscores)
    tier = job.tier
    if data.get("excluded_role_type"):
        score = min(score, 15)
        job.exclude_tag = "excluded-role-type"
    if data.get("intl_onsite_no_india") and tier not in ("strong-fit", "reach"):
        score = min(score, 25)
        job.exclude_tag = job.exclude_tag or "intl-onsite"
    if data.get("unmet_must_have"):
        score = min(score, 30)
        blk = str(data.get("blocker", "")).strip()
        job.exclude_tag = job.exclude_tag or ("unmet-must-have" + (f": {blk}" if blk else ""))
    return max(0, min(100, score))


def _fallback(job: Job, settings) -> None:
    """Heuristic score if the LLM is unavailable — rough, flagged in rationale."""
    sub = {
        "role_type": 0.5, "domain": 0.5,
        "seniority": 0.0 if job.seniority == "Junior" else 0.7,
        "company": {"strong-fit": 1.0, "reach": 0.8, "safe": 0.5}.get(job.tier, 0.4),
        "location": 1.0 if job.remote else (0.9 if _is_india(job, settings) else 0.2),
        "feasibility": 1.0,
    }
    job.subscores = sub
    job.match_score = _weighted(sub)
    job.band = _band(job.match_score)
    job.rationale = "Heuristic fallback (LLM scoring unavailable)."
    if job.description.strip():
        job.summary = " ".join(job.description.split())[:280]
    else:
        job.summary = f"{job.title} at {job.company}. Full JD not provided by source."


def _score_call(client, prompt: str) -> dict:
    """One scoring call; on malformed JSON, one corrective retry, then raise."""
    resp = client.messages.create(
        model=SUMMARY_MODEL, max_tokens=800, system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        return _parse_json(resp.content[0].text)
    except (json.JSONDecodeError, ValueError):
        resp = client.messages.create(
            model=SUMMARY_MODEL, max_tokens=800, system=_SYSTEM,
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
    profile = load_profile() or "(no profile provided)"
    for job in jobs:
        if client is None:
            _fallback(job, settings)
            continue
        prompt = _PROMPT.format(
            profile=profile, rubric=_RUBRIC,
            title=job.title, company=job.company, tier=job.tier or "not listed",
            location=job.location or "(unspecified)", remote=job.remote,
            india=_is_india(job, settings), seniority=job.seniority or "(unknown)",
            jd=(job.description or job.title)[:6000],
        )
        try:
            data = _score_call(client, prompt)
            job.summary = str(data.get("summary", "")).strip()
            job.requirements = [str(r).strip() for r in data.get("requirements", []) if str(r).strip()][:8]
            job.subscores = {d: float(data.get("subscores", {}).get(d, 0) or 0) for d in WEIGHTS}
            job.rationale = str(data.get("rationale", "")).strip()
            job.fit_reason = str(data.get("fit_reason", "")).strip()
            job.gap_risk = str(data.get("gap_risk", "")).strip()
            job.match_score = _apply_gates(job, data, settings)
            job.band = _band(job.match_score)
            if not job.summary:
                job.summary = f"{job.title} at {job.company}."
        except Exception as exc:
            log.warning("Scoring failed for %r @ %s: %s", job.title, job.company, exc)
            _fallback(job, settings)
