"""Configuration: env vars, the targets.yaml search spec, and the profile."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
OUT_DIR = ROOT / "out"

load_dotenv(ROOT / ".env")

# The Google Sheet that is the single system of record + dedupe memory.
# Overridable via env; defaults to the sheet created during setup.
DEFAULT_SHEET_ID = "1mTNmTNJOnaUq-31XfapO36ZSY2CNLZP_7isq3KJTN3A"

# Model used for role summaries + the weekly requirements analysis.
SUMMARY_MODEL = os.environ.get("SUMMARY_MODEL", "claude-sonnet-5-5")

# Worksheet names inside the Sheet.
JOBS_TAB = "Jobs"
META_TAB = "_meta"

# Match-score delivery thresholds and band cutoffs (0–100 fit score).
SEND_THRESHOLD = 65        # email roles scoring at/above this (Good and Strong)
STORE_THRESHOLD = 45       # store Marginal+ in the Sheet; drop Low entirely
BANDS = [(80, "Strong"), (65, "Good"), (45, "Marginal"), (0, "Low")]

# Column order for the Jobs worksheet (the system of record).
COLUMNS = [
    "Date added",
    "Source platform",
    "Company",
    "Tier",
    "Title",
    "Location",
    "Remote?",
    "Posted date",
    "Seniority",
    "Salary/comp",
    "Match score",
    "Band",
    "Top fit reason",
    "Top gap/risk",
    "Short summary",
    "Key requirements/skills",
    "Full JD",
    "Apply URL",
    "Sent in digest?",
    "Role-type",        # the six sub-scores (0–1), stored for transparency/tuning
    "Domain",
    "Seniority score",
    "Company score",
    "Location score",
    "Feasibility",
    "Rationale",
    "Dedupe key",
]


@dataclass
class Platform:
    name: str
    enabled: bool
    actor: str
    results_per_query: int
    input: dict
    fields: dict = field(default_factory=dict)
    root: str = ""          # sub-object key to descend into before field extraction


@dataclass
class Settings:
    recency_days: int
    max_items_per_digest: int
    weekly_interval_days: int
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
    companies: dict          # tier -> [names]
    platforms: list[Platform]
    ats_boards: dict         # provider -> [{company, slug}]


def load_settings() -> Settings:
    raw = yaml.safe_load((CONFIG_DIR / "targets.yaml").read_text())
    platforms = [
        Platform(
            name=p["name"],
            enabled=bool(p.get("enabled", False)),
            actor=p.get("actor", ""),
            results_per_query=int(p.get("results_per_query", 25)),
            input=p.get("input", {}) or {},
            fields=p.get("fields", {}) or {},
            root=p.get("root", "") or "",
        )
        for p in raw.get("platforms", [])
    ]
    return Settings(
        recency_days=int(raw.get("recency_days", 14)),
        max_items_per_digest=int(raw.get("max_items_per_digest", 25)),
        weekly_interval_days=int(raw.get("weekly_interval_days", 7)),
        default_location=raw.get("default_location", "India"),
        search_queries=raw.get("search_queries", []),
        target_titles=raw.get("target_titles", []),
        pm_terms=[t.lower() for t in raw.get("pm_terms", [])],
        solutions_terms=[t.lower() for t in raw.get("solutions_terms", [])],
        ai_terms=[t.lower() for t in raw.get("ai_terms", [])],
        exclude_titles=[t.lower() for t in raw.get("exclude_titles", [])],
        code_gate_terms=[t.lower() for t in raw.get("code_gate_terms", [])],
        senior_terms=[t.lower() for t in raw.get("senior_terms", [])],
        junior_terms=[t.lower() for t in raw.get("junior_terms", [])],
        india_terms=[t.lower() for t in raw.get("india_terms", [])],
        remote_terms=[t.lower() for t in raw.get("remote_terms", [])],
        companies={tier: list(names) for tier, names in raw.get("companies", {}).items()},
        platforms=platforms,
        ats_boards=raw.get("ats_boards", {}) or {},
    )


def load_profile() -> str:
    path = CONFIG_DIR / "profile.md"
    return path.read_text().strip() if path.exists() else ""


def sheet_id() -> str:
    # An unset *or empty* env var (e.g. an undefined GitHub secret) falls back.
    return os.environ.get("JOBS_SHEET_ID", "").strip() or DEFAULT_SHEET_ID


def sheet_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id()}/edit"


def env(name: str, required: bool = False) -> str:
    value = os.environ.get(name, "")
    if required and not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value
