#!/usr/bin/env python3
"""Run the AI-PM job-search digest pipeline.

Usage:
  python run_scraper.py                # full run: discover, store, email
  python run_scraper.py --dry-run      # render out/digest.html; no Sheet, no email
  python run_scraper.py --no-apify     # ATS career pages only (skip paid actors)
  python run_scraper.py --no-ats       # Apify platforms only (skip ATS boards)
  python run_scraper.py --no-llm       # skip summaries/weekly analysis (fallback text)
"""

import argparse
import logging
import sys

from job_digest.pipeline import run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Render out/digest.html instead of writing the Sheet / emailing")
    parser.add_argument("--no-apify", action="store_true", help="Skip Apify platforms")
    parser.add_argument("--no-ats", action="store_true", help="Skip ATS career-page boards")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip LLM summaries and the weekly analysis")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run(dry_run=args.dry_run, use_apify=not args.no_apify,
        use_ats=not args.no_ats, use_llm=not args.no_llm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
