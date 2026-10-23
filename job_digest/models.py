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

    # Derived by summarize.py
    summary: str = ""
    requirements: list[str] = field(default_factory=list)

    dedupe_key: str = ""

    # Set when the same company+title spans several locations and is collapsed
    # to one line in the email (all variants still stored in the Sheet).
    variant_count: int = 1
    variant_keys: list[str] = field(default_factory=list)

    def remote_label(self) -> str:
        return "Yes" if self.remote else "No"
