#!/usr/bin/env python3
"""One-shot Apify connectivity + schema check for a configured platform.

The actors' output schemas aren't documented, so before enabling a platform
confirm the pipeline parses its records. This runs the platform's actor once
with a small result count and prints the raw record shape plus how the parser
reads it.

Usage:
  APIFY_TOKEN=... python scripts/test_apify.py linkedin "AI Product Manager"
  APIFY_TOKEN=... python scripts/test_apify.py indeed   "AI Product Manager"
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from job_digest import discovery          # noqa: E402
from job_digest.config import load_settings   # noqa: E402


def main() -> int:
    token = os.environ.get("APIFY_TOKEN", "")
    if not token:
        print("Set APIFY_TOKEN in the environment first.", file=sys.stderr)
        return 1

    platform_name = sys.argv[1] if len(sys.argv) > 1 else "linkedin"
    query = sys.argv[2] if len(sys.argv) > 2 else "AI Product Manager"

    settings = load_settings()
    platform = next((p for p in settings.platforms if p.name == platform_name), None)
    if platform is None:
        print(f"Unknown platform {platform_name!r}. Known: "
              f"{[p.name for p in settings.platforms]}", file=sys.stderr)
        return 1
    if not platform.actor:
        print(f"Platform {platform_name!r} has no actor id set in config/targets.yaml.")
        return 1

    run_input = discovery._subst(dict(platform.input), query, settings.default_location)
    # Trim result counts for a cheap probe.
    for k in ("rows", "maxItems", "total_posts", "maxResults"):
        if k in run_input:
            run_input[k] = 5

    print(f"Running actor {platform.actor!r} for {query!r} ...\n")
    records = discovery.run_actor(token, platform.actor, run_input)
    print(f"Got {len(records)} record(s).\n")
    if not records:
        print("No records. Try a broader query or check the actor's input schema.")
        return 0

    print("=== Raw keys on first record ===")
    print(sorted(records[0].keys()))
    print("\n=== First record (pretty, truncated) ===")
    print(json.dumps(records[0], indent=2, default=str)[:3000])

    print("\n=== How the pipeline parses each record ===")
    for i, rec in enumerate(records):
        job = discovery._record_to_job(rec, platform)
        if job is None:
            print(f"[{i}] MISSING title/url")
            continue
        print(f"[{i}] OK | {job.title[:50]!r} @ {job.company[:30]!r} | {job.location[:30]!r} "
              f"| ts={job.posted_ts:.0f} | url={job.url[:60]!r}")

    print("\nIf records show MISSING or blank company/location, add the real field names to "
          f"that platform's `fields` map in config/targets.yaml (keys are printed above).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
