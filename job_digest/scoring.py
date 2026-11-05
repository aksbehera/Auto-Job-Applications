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

_SYSTEM = (
    "You are a sharp technical recruiter scoring AI / product roles for one "
    "specific candidate. Judge TRUE fit by reading the job description's must-have "
    "requirements, never by the title alone. Takeability from India is decisive: a "
    "role he cannot physically take from India now must never score like one he "
    "can, however strong the company. Be decisive and honest. Return only JSON."
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

seniority — LEVEL and comp fit vs ~11 years / manager; money matters more than
  title to him, so a below-level or low-comp role is a real miss even if the AI
  fit is perfect.
  1.0 manager/senior/lead/staff pitched at ~8–15 yrs; 0.5 slightly off (15+ yrs
  required, or a borderline senior-IC); 0.3 clearly below his level (PM I, PM II,
  "3–5 years", mid-level); 0.1 intern/junior or Director/VP-only.

company — quality, AI-nativeness, and likely pay.
  1.0 strong-fit target; 0.8 reach target; 0.7 strong non-listed AI-native;
  0.5 safe/listed; 0.4 or less for IT-services / staffing / pure-delivery shops
  where a market-priced Salesforce-equivalent move is unlikely (even if listed);
  0.3 ordinary/unknown. (Tier hint is provided; judge AI-nativeness from the JD.)

location — 1.0 remote and India-eligible; 0.9 India on-site/hybrid; 0.5
  international remote that plausibly hires in India; 0.1 international on-site,
  US-state-locked, or US-only "remote" with no India path.

feasibility — 1.0 no blockers; lower for visa-required international with no stated
  India hiring/sponsorship, immediate/0–15-day-joiner demands (he has a notice
  period), likely-below-market comp, or a hard must-have he lacks (he does NOT
  hand-write production code or train models).

Also set these judgements (booleans):
  takeable — true if the role is India-located OR remote-and-India-eligible.
             false if it is international on-site, US-state-locked, or US-only
             "remote" with no stated India hiring or visa sponsorship. Company
             prestige does NOT make a role takeable.
  excluded_role_type — true if role_type is 0 (code-gated eng / ML-eng /
             data-architect / IC DS / non-AI or generic PM).
  unmet_must_have — true if a stated hard must-have is something he lacks; put it
             in "blocker".
  partial_jd — true if the job description looks truncated or is only a short
             snippet, so your scoring is uncertain."""

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


def _weighted(sub: dict) -> int:
    total = sum(WEIGHTS[d] * max(0.0, min(1.0, float(sub.get(d, 0) or 0))) for d in WEIGHTS)
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


def _apply_gates(job: Job, data: dict) -> int:
    """Raw weighted score, then hard caps; sets job.raw_score and exclude tags."""
    raw = _weighted(job.subscores)
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


def _fallback(job: Job, settings) -> None:
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
    job.raw_score = _weighted(sub)
    job.match_score = min(job.raw_score, NOT_TAKEABLE_CAP) if not job.takeable else job.raw_score
    job.band = _band(job.match_score)
    job.provisional = len((job.description or "").strip()) < PARTIAL_JD_CHARS
    job.rationale = "Heuristic fallback (LLM scoring unavailable)."
    job.summary = (" ".join(job.description.split())[:280] if job.description.strip()
                   else f"{job.title} at {job.company}. Full JD not provided by source.")


def _score_call(client, prompt: str) -> dict:
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
            jd=(job.description or job.title)[:JD_CHARS],
        )
        try:
            data = _score_call(client, prompt)
            job.summary = str(data.get("summary", "")).strip()
            job.requirements = [str(r).strip() for r in data.get("requirements", []) if str(r).strip()][:8]
            job.subscores = {d: float(data.get("subscores", {}).get(d, 0) or 0) for d in WEIGHTS}
            job.rationale = str(data.get("rationale", "")).strip()
            job.fit_reason = str(data.get("fit_reason", "")).strip()
            job.gap_risk = str(data.get("gap_risk", "")).strip()
            job.takeable = bool(data.get("takeable", True))
            job.match_score = _apply_gates(job, data)
            job.band = _band(job.match_score)
            job.provisional = bool(data.get("partial_jd")) or \
                len((job.description or "").strip()) < PARTIAL_JD_CHARS
            if not job.summary:
                job.summary = f"{job.title} at {job.company}."
        except Exception as exc:
            log.warning("Scoring failed for %r @ %s: %s", job.title, job.company, exc)
            _fallback(job, settings)
