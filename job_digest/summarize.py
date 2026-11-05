"""LLM summaries: a 2–3 sentence role summary + parsed key requirements.

Runs once per new job. The full JD stays in the Sheet; only the short summary
goes into the email. Failures are non-fatal — the job still stores with a
truncated-JD fallback summary.
"""

import json
import logging

from .config import SUMMARY_MODEL
from .models import Job

log = logging.getLogger(__name__)

_SYSTEM = (
    "You summarise job descriptions for a busy AI/Technical Product Manager "
    "screening roles. Be concise, concrete, and faithful to the JD. Never invent "
    "requirements that aren't in the text."
)

_PROMPT = """Here is a job posting.

Title: {title}
Company: {company}
Location: {location}

Job description:
\"\"\"
{description}
\"\"\"

Return ONLY a JSON object with exactly these keys:
- "summary": 2-3 sentences — what the role is and its single most important
  requirement/focus. No fluff, no "This role is...".
- "requirements": an array of 4-8 short strings — the key required skills,
  tools, and experience, each a few words (e.g. "5+ yrs product management",
  "LLM/RAG systems", "SQL", "enterprise SaaS").

Output the JSON and nothing else."""


def _fallback(job: Job) -> None:
    if job.description.strip():
        snippet = " ".join(job.description.split())[:280]
        job.summary = snippet + ("…" if len(job.description) > 280 else "")
    else:
        # Some sources (e.g. Foundit) don't expose the JD text; keep the card useful.
        loc = f", {job.location}" if job.location else ""
        job.summary = (f"{job.title} at {job.company}{loc}. "
                       f"Full description not provided by the source — open the apply link.")
    job.requirements = []


def summarize_jobs(client, jobs: list[Job]) -> None:
    for job in jobs:
        if not job.description:
            _fallback(job)
            continue
        prompt = _PROMPT.format(
            title=job.title, company=job.company, location=job.location,
            description=job.description[:6000],
        )
        try:
            resp = client.messages.create(
                model=SUMMARY_MODEL,
                max_tokens=600,
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            text = text[text.find("{"): text.rfind("}") + 1]
            data = json.loads(text)
            job.summary = str(data.get("summary", "")).strip()
            reqs = data.get("requirements", [])
            job.requirements = [str(r).strip() for r in reqs if str(r).strip()][:8]
            if not job.summary:
                _fallback(job)
        except Exception as exc:
            log.warning("Summary failed for %r @ %s: %s", job.title, job.company, exc)
            _fallback(job)
