#!/usr/bin/env python3
"""Run a job-search digest pipeline for one person (profile).

Usage:
  python run_scraper.py --profile akshit      # full run: discover, score, store, email
  python run_scraper.py --profile deepanshi
  python run_scraper.py --profile akshit --dry-run   # render out/digest_<profile>.html only
  python run_scraper.py --profile akshit --no-apify  # ATS career pages only (skip paid actors)
  python run_scraper.py --profile akshit --no-ats    # Apify platforms only (skip ATS boards)
  python run_scraper.py --profile akshit --no-llm    # skip scoring/weekly analysis (fallback)

The profile also comes from the JOB_PROFILE env var; it defaults to 'akshit'.
"""

import argparse
import logging
import sys

from job_digest.pipeline import run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", default=None,
                        help="Which person's search to run (e.g. akshit, deepanshi). "
                             "Defaults to $JOB_PROFILE or 'akshit'.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Render out/digest_<profile>.html instead of writing the Sheet / emailing")
    parser.add_argument("--no-apify", action="store_true", help="Skip Apify platforms")
    parser.add_argument("--no-ats", action="store_true", help="Skip ATS career-page boards")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip LLM scoring and the weekly analysis")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run(profile=args.profile, dry_run=args.dry_run, use_apify=not args.no_apify,
        use_ats=not args.no_ats, use_llm=not args.no_llm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
