"""The Job record that flows through the pipeline."""

from dataclasses import dataclass, field


@dataclass
class Job:
    source: str                 # platform / ATS provider the role came from
    company: str
    title: str
    location: str
    url: str                    # full apply URL, kept intact
    description: str            # full JD (plain text)
    posted_ts: float = 0.0      # unix seconds, 0 if unknown
    salary: str = ""
    seniority: str = ""         # raw hint from the source, if any

    # Derived by classify.py
    remote: bool = False
    tier: str = ""              # "strong-fit" | "reach" | "safe" | "" (non-target)
    group: str = ""             # "target" | "remote" | "india"
    score: float = 0.0

    # Derived by scoring.py
    summary: str = ""
    requirements: list[str] = field(default_factory=list)
    match_score: int = 0                       # 0–100 overall fit
    band: str = ""                             # Strong | Good | Marginal | Low
    subscores: dict = field(default_factory=dict)   # the 6 weighted dimensions (0–1)
    rationale: str = ""                        # one-line "why this score"
    fit_reason: str = ""                       # single biggest fit reason
    gap_risk: str = ""                         # single biggest gap or risk
    exclude_tag: str = ""                      # set when a hard gate fires

    dedupe_key: str = ""

    # Set when the same company+title spans several locations and is collapsed
    # to one line in the email (all variants still stored in the Sheet).
    variant_count: int = 1
    variant_keys: list[str] = field(default_factory=list)

    def remote_label(self) -> str:
        return "Yes" if self.remote else "No"
