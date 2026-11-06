"""Configuration: env vars + a per-person profile (search spec, sheet, rubric).

Each person is a profile directory under profiles/<name>/ holding targets.yaml
(the search spec + identity), profile.md (the candidate profile) and rubric.md
(the LLM scoring rubric). The active profile is chosen by --profile / JOB_PROFILE,
so two people's searches stay completely separate: separate config, separate
Google Sheet, separate recipient.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = ROOT / "profiles"
OUT_DIR = ROOT / "out"
DEFAULT_PROFILE = "akshit"

load_dotenv(ROOT / ".env")

# Model used for scoring + the weekly requirements analysis.
SUMMARY_MODEL = os.environ.get("SUMMARY_MODEL", "claude-sonnet-5-5")

# Worksheet names inside each Sheet.
JOBS_TAB = "Jobs"
META_TAB = "_meta"

# Match-score delivery thresholds and band cutoffs (0–100 fit score).
SEND_THRESHOLD = 70          # email takeable roles scoring at/above this (Good+)
STORE_THRESHOLD = 55         # store Marginal+ in the Sheet; drop Low entirely
ASPIRATIONAL_THRESHOLD = 70  # show not-takeable roles whose UNCAPPED fit is this high
BANDS = [(85, "Strong"), (70, "Good"), (55, "Marginal"), (0, "Low")]

# Default dimension weights (sum to 100). A profile may override via `weights:`
# in its targets.yaml (e.g. a sales profile that cares more about company brand).
DEFAULT_WEIGHTS = {
    "role_type": 30, "domain": 20, "seniority": 15,
    "company": 15, "location": 15, "feasibility": 5,
}

# Column order for the Jobs worksheet (the system of record).
COLUMNS = [
    "Date added", "Source platform", "Company", "Tier", "Title", "Location",
    "Remote?", "Posted date", "Seniority", "Salary/comp", "Match score", "Band",
    "Takeable", "Raw score", "Top fit reason", "Top gap/risk", "Short summary",
    "Key requirements/skills", "Full JD", "Apply URL", "Sent in digest?",
    "Role-type", "Domain", "Seniority score", "Company score", "Location score",
    "Feasibility", "Rationale", "Dedupe key",
]


@dataclass
class Platform:
    name: str
    enabled: bool
    actor: str
    results_per_query: int
    input: dict
    fields: dict = field(default_factory=dict)
    root: str = ""


@dataclass
class Settings:
    profile: str
    sheet_id: str
    digest_recipient: str
    digest_title: str
    scoring_system: str
    scoring_rubric: str
    weights: dict
    recency_days: int
    max_items_per_digest: int
    weekly_interval_days: int
    require_domain_signal: bool   # pre-filter needs a domain cue in the title/JD (e.g. "AI")
    default_location: str
    search_queries: list[str]
    target_titles: list[str]
    pm_terms: list[str]
    solutions_terms: list[str]
    ai_terms: list[str]
    exclude_titles: list[str]
    code_gate_terms: list[str]
    senior_terms: list[str]
    junior_terms: list[str]
    india_terms: list[str]
    remote_terms: list[str]
    companies: dict
    platforms: list[Platform]
    ats_boards: dict

    @property
    def sheet_url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.sheet_id}/edit"


def _profile_dir(profile: str) -> Path:
    return PROFILES_DIR / profile


def resolve_profile(profile: str | None = None) -> str:
    return profile or os.environ.get("JOB_PROFILE", "").strip() or DEFAULT_PROFILE


def load_settings(profile: str | None = None) -> Settings:
    profile = resolve_profile(profile)
    pdir = _profile_dir(profile)
    path = pdir / "targets.yaml"
    if not path.exists():
        raise SystemExit(f"Unknown profile {profile!r}: {path} not found. "
                         f"Available: {[p.name for p in PROFILES_DIR.iterdir() if p.is_dir()]}")
    raw = yaml.safe_load(path.read_text())
    platforms = [
        Platform(
            name=p["name"], enabled=bool(p.get("enabled", False)),
            actor=p.get("actor", ""), results_per_query=int(p.get("results_per_query", 25)),
            input=p.get("input", {}) or {}, fields=p.get("fields", {}) or {},
            root=p.get("root", "") or "",
        )
        for p in raw.get("platforms", [])
    ]
    rubric_path = pdir / "rubric.md"
    scoring_rubric = rubric_path.read_text().strip() if rubric_path.exists() else ""
    lower = lambda key: [t.lower() for t in raw.get(key, [])]
    return Settings(
        profile=profile,
        sheet_id=str(raw.get("sheet_id", "")),
        digest_recipient=str(raw.get("digest_recipient", "")),
        digest_title=str(raw.get("digest_title", "Job Digest")),
        scoring_system=str(raw.get("scoring_system", "")).strip(),
        scoring_rubric=scoring_rubric,
        weights={**DEFAULT_WEIGHTS, **{k: int(v) for k, v in (raw.get("weights") or {}).items()}},
        recency_days=int(raw.get("recency_days", 14)),
        max_items_per_digest=int(raw.get("max_items_per_digest", 25)),
        weekly_interval_days=int(raw.get("weekly_interval_days", 7)),
        require_domain_signal=bool(raw.get("require_domain_signal", True)),
        default_location=raw.get("default_location", "India"),
        search_queries=raw.get("search_queries", []),
        target_titles=raw.get("target_titles", []),
        pm_terms=lower("pm_terms"),
        solutions_terms=lower("solutions_terms"),
        ai_terms=lower("ai_terms"),
        exclude_titles=lower("exclude_titles"),
        code_gate_terms=lower("code_gate_terms"),
        senior_terms=lower("senior_terms"),
        junior_terms=lower("junior_terms"),
        india_terms=lower("india_terms"),
        remote_terms=lower("remote_terms"),
        companies={tier: list(names) for tier, names in raw.get("companies", {}).items()},
        platforms=platforms,
        ats_boards=raw.get("ats_boards", {}) or {},
    )


def load_profile(profile: str | None = None) -> str:
    path = _profile_dir(resolve_profile(profile)) / "profile.md"
    return path.read_text().strip() if path.exists() else ""


def env(name: str, required: bool = False) -> str:
    value = os.environ.get(name, "")
    if required and not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value
