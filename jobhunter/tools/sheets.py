"""Application log: Google Sheets if configured, else a local CSV."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from ..config import ENV
from ..state import Job

HEADERS = ["timestamp", "source", "job_id", "title", "company", "location",
           "url", "score", "reason", "status", "note", "cover_letter"]


class AppLog:
    def __init__(self) -> None:
        self.ws = None
        if ENV.sa_file and ENV.sheet_id and Path(ENV.sa_file).exists():
            import gspread
            gc = gspread.service_account(filename=ENV.sa_file)
            sh = gc.open_by_key(ENV.sheet_id)
            try:
                self.ws = sh.worksheet("Applications")
            except gspread.WorksheetNotFound:
                self.ws = sh.add_worksheet("Applications", rows=1000, cols=len(HEADERS))
            if self.ws.row_values(1) != HEADERS:
                self.ws.update("A1", [HEADERS])
        else:
            self.csv_path = Path("applications.csv")
            if not self.csv_path.exists():
                with self.csv_path.open("w", newline="") as f:
                    csv.writer(f).writerow(HEADERS)

    @property
    def backend(self) -> str:
        return "Google Sheets" if self.ws else f"CSV ({self.csv_path})"

    def seen_keys(self) -> set[str]:
        """source:job_id for every job already logged, so we never re-process."""
        if self.ws:
            rows = self.ws.get_all_values()[1:]
        else:
            with self.csv_path.open() as f:
                rows = list(csv.reader(f))[1:]
        return {f"{r[1]}:{r[2]}" for r in rows if len(r) > 2}

    def append(self, job: Job) -> None:
        row = [datetime.now().isoformat(timespec="seconds")] + [
            str(job.get(h, "")) for h in HEADERS[1:]
        ]
        if self.ws:
            self.ws.append_row(row, value_input_option="RAW")
        else:
            with self.csv_path.open("a", newline="") as f:
                csv.writer(f).writerow(row)
