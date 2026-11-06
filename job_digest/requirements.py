"""Weekly requirements analysis across all stored JDs.

Aggregates every full JD in the Sheet and asks the model for the market picture
— common skills/tools, recurring responsibilities, seniority & comp bands — and
the gaps between that and the owner's profile keywords. Returns an HTML block
the emailer drops in alongside the digest on weekly runs.
"""

import logging

from .config import SUMMARY_MODEL, load_profile

log = logging.getLogger(__name__)

_SYSTEM = (
    "You are a sharp career analyst helping an AI/Technical Product Manager "
    "understand the market for AI PM roles in India and remotely. Be specific "
    "and quantitative where the data allows; never pad."
)

_PROMPT = """Below are {n} job descriptions (title · company · location, then JD)
for AI / Technical Product Manager-type roles collected over recent weeks, then
the candidate's own profile.

=== JOB DESCRIPTIONS ===
{jds}

=== CANDIDATE PROFILE ===
{profile}

Produce a tight analysis with these four sections, as plain prose + short
bullet lists (no markdown headers, no preamble):

1. Most common required skills & tools — ranked, with rough frequency.
2. Recurring responsibilities — what these roles actually expect day to day.
3. Typical seniority & compensation bands — only where the JDs state them;
   say "not disclosed" rather than guessing.
4. Gaps vs the candidate's profile — concrete keywords/skills showing up often
   that are NOT in the candidate's profile, i.e. what to shore up.

Return ONLY the analysis text."""


def _jd_blob(all_rows: list[dict], limit: int = 60, per_jd_chars: int = 1500) -> tuple[str, int]:
    rows = all_rows[-limit:] if len(all_rows) > limit else all_rows
    chunks = []
    for r in rows:
        jd = str(r.get("Full JD", "")).strip()
        if not jd:
            continue
        head = f"{r.get('Title','')} · {r.get('Company','')} · {r.get('Location','')}"
        chunks.append(f"{head}\n{jd[:per_jd_chars]}")
    return "\n\n---\n\n".join(chunks), len(chunks)


def analyse(client, all_rows: list[dict], settings) -> str:
    """Return the analysis as plain text, or '' if there's nothing to analyse."""
    jds, n = _jd_blob(all_rows)
    if n == 0:
        return ""
    prompt = _PROMPT.format(n=n, jds=jds,
                            profile=load_profile(settings.profile) or "(no profile provided)")
    try:
        resp = client.messages.create(
            model=SUMMARY_MODEL,
            max_tokens=1600,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as exc:
        log.warning("Weekly analysis failed: %s", exc)
        return ""
