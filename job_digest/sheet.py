"""Google Sheet access — the single system of record and dedupe memory.

Auth is a Google service account, supplied either as raw JSON in
GOOGLE_SERVICE_ACCOUNT_JSON or as a file path in GOOGLE_SERVICE_ACCOUNT_FILE.
The service account's client_email must have edit access to the Sheet.
"""

import json
import logging
import os
import time

import gspread
from google.oauth2.service_account import Credentials

from .config import COLUMNS, JOBS_TAB, META_TAB, sheet_id
from .models import Job

log = logging.getLogger(__name__)

# Google Sheets hard-caps a cell at 50,000 characters; keep JDs safely under it.
MAX_CELL_CHARS = 49000

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
SENT_COL = COLUMNS.index("Sent in digest?") + 1   # 1-based for gspread


def _credentials() -> Credentials:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        info = json.loads(raw)
        return Credentials.from_service_account_info(info, scopes=SCOPES)
    path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if path:
        return Credentials.from_service_account_file(path, scopes=SCOPES)
    raise SystemExit(
        "No Google service-account credentials. Set GOOGLE_SERVICE_ACCOUNT_JSON "
        "(raw JSON) or GOOGLE_SERVICE_ACCOUNT_FILE (path)."
    )


class JobSheet:
    """Thin wrapper over the Jobs + _meta worksheets."""

    def __init__(self):
        self.client = gspread.authorize(_credentials())
        self.doc = self.client.open_by_key(sheet_id())
        self.jobs = self._ensure_tab(JOBS_TAB, header=COLUMNS)
        self.meta = self._ensure_tab(META_TAB, header=["key", "value"])

    def _ensure_tab(self, title: str, header: list[str]):
        try:
            ws = self.doc.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = self.doc.add_worksheet(title=title, rows=1000, cols=max(20, len(header)))
        existing = ws.row_values(1)
        if existing[: len(header)] != header:
            ws.update(values=[header], range_name="A1")
            if title == JOBS_TAB:
                ws.freeze(rows=1)
        return ws

    # -------------------------------------------------- dedupe memory

    def existing_keys(self) -> set[str]:
        """Every dedupe key already stored, so we never re-add a known role."""
        try:
            col = COLUMNS.index("Dedupe key") + 1
            values = self.jobs.col_values(col)[1:]   # skip header
        except Exception as exc:
            log.warning("Could not read dedupe keys: %s", exc)
            return set()
        return {v.strip() for v in values if v.strip()}

    # -------------------------------------------------- writes

    def append_jobs(self, jobs: list[Job]) -> None:
        if not jobs:
            return
        today = time.strftime("%Y-%m-%d")
        rows = []
        for j in jobs:
            rows.append([
                today,
                j.source,
                j.company,
                j.tier or "—",
                j.title,
                j.location,
                j.remote_label(),
                _posted_str(j.posted_ts),
                j.seniority,
                j.salary,
                j.summary,
                j.description[:MAX_CELL_CHARS],
                "; ".join(j.requirements),
                j.url,
                "N",
                f"{j.score:.3f}",
                j.dedupe_key,
            ])
        self.jobs.append_rows(rows, value_input_option="RAW")
        log.info("Appended %d new jobs to the Sheet", len(rows))

    def unsent_rows(self) -> list[dict]:
        """All rows whose 'Sent in digest?' is not yet Y, with their row number."""
        records = self.jobs.get_all_records(expected_headers=COLUMNS)
        out = []
        for i, rec in enumerate(records, start=2):   # row 1 is the header
            sent = str(rec.get("Sent in digest?", "")).strip().upper()
            if not sent.startswith("Y"):
                rec["_row"] = i
                out.append(rec)
        return out

    def mark_sent(self, row_numbers: list[int]) -> None:
        if not row_numbers:
            return
        stamp = f"Y {time.strftime('%Y-%m-%d')}"
        updates = [{
            "range": gspread.utils.rowcol_to_a1(r, SENT_COL),
            "values": [[stamp]],
        } for r in row_numbers]
        self.jobs.batch_update(updates)
        log.info("Marked %d rows as sent", len(row_numbers))

    def all_jobs(self) -> list[dict]:
        return self.jobs.get_all_records(expected_headers=COLUMNS)

    # -------------------------------------------------- meta (weekly cadence)

    def meta_get(self, key: str) -> str:
        for rec in self.meta.get_all_records(expected_headers=["key", "value"]):
            if rec.get("key") == key:
                return str(rec.get("value", ""))
        return ""

    def meta_set(self, key: str, value: str) -> None:
        rows = self.meta.get_all_values()
        for i, row in enumerate(rows[1:], start=2):   # skip header
            if row and row[0] == key:
                self.meta.update_cell(i, 2, value)
                return
        self.meta.append_row([key, value], value_input_option="RAW")


def _posted_str(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts)) if ts else ""
