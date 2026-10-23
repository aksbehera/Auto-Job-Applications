#!/usr/bin/env python3
"""Verify Google Sheet access and print the service-account email to share with.

Usage:
  GOOGLE_SERVICE_ACCOUNT_FILE=sa.json python scripts/check_sheet.py
  # or GOOGLE_SERVICE_ACCOUNT_JSON='{...}' python scripts/check_sheet.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _sa_email() -> str:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        return json.loads(raw).get("client_email", "?")
    path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if path and os.path.exists(path):
        return json.load(open(path)).get("client_email", "?")
    return "?"


def main() -> int:
    from job_digest.config import sheet_id, sheet_url

    print(f"Service account: {_sa_email()}")
    print(f"Sheet id:        {sheet_id()}")
    print(f"Sheet URL:       {sheet_url()}")
    print("\nThe service account above must have Editor access to that Sheet.\n")

    try:
        from job_digest.sheet import JobSheet
        sheet = JobSheet()
        keys = sheet.existing_keys()
        unsent = sheet.unsent_rows()
        print("OK — connected to the Sheet.")
        print(f"   Jobs tab header is in place; {len(keys)} stored role(s), "
              f"{len(unsent)} not yet sent.")
        return 0
    except Exception as exc:
        print(f"FAILED to access the Sheet: {exc}")
        print("\nChecklist:")
        print("  1. Is the Google Sheets + Drive API enabled on the service account's project?")
        print("  2. Did you share the Sheet with the service-account email above (Editor)?")
        print("  3. Is JOBS_SHEET_ID correct (or left as the default)?")
        return 1


if __name__ == "__main__":
    sys.exit(main())
