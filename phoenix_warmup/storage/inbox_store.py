"""
storage/inbox_store.py
Thread-safe CRUD operations for inboxes.csv.
Uses a module-level threading.Lock to prevent concurrent write corruption.
"""
import csv
import threading
from dataclasses import dataclass, asdict, fields
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Resolve data directory (PyInstaller-safe)
import sys

def _get_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent.parent
    d = base / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d

CSV_PATH = _get_data_dir() / "inboxes.csv"

HEADERS = [
    "email", "smtp_host", "smtp_port", "imap_host", "imap_port",
    "password", "stage", "daily_sent", "daily_limit", "status",
    "last_sent_at", "paused_reason", "working_hours_start", "working_hours_end",
]

_lock = threading.Lock()


@dataclass
class InboxRecord:
    email: str
    smtp_host: str = "smtp.zoho.in"
    smtp_port: int = 587
    imap_host: str = "imap.zoho.in"
    imap_port: int = 993
    password: str = ""
    stage: int = 1
    daily_sent: int = 0
    daily_limit: int = 5
    status: str = "active"          # active | paused | error | warming
    last_sent_at: str = ""
    paused_reason: str = ""
    working_hours_start: str = "08:00"
    working_hours_end: str = "18:00"

    def __post_init__(self):
        # Coerce types read from CSV strings
        self.smtp_port = int(self.smtp_port)
        self.imap_port = int(self.imap_port)
        self.stage = int(self.stage)
        self.daily_sent = int(self.daily_sent)
        self.daily_limit = int(self.daily_limit)


class InboxStore:
    """Thread-safe CSV-backed store for inbox accounts."""

    # ------------------------------------------------------------------ #
    # Private helpers                                                       #
    # ------------------------------------------------------------------ #

    def _ensure_file(self) -> None:
        """Create CSV with header row if it doesn't exist."""
        if not CSV_PATH.exists():
            with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=HEADERS)
                writer.writeheader()

    def _read_raw(self) -> List[dict]:
        """Read all rows as plain dicts. Caller MUST hold _lock."""
        self._ensure_file()
        with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _write_raw(self, rows: List[dict]) -> None:
        """Overwrite CSV with given rows. Caller MUST hold _lock."""
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerows(rows)

    def _row_to_record(self, row: dict) -> InboxRecord:
        return InboxRecord(**{k: row.get(k, "") for k in HEADERS})

    # ------------------------------------------------------------------ #
    # Public API                                                            #
    # ------------------------------------------------------------------ #

    def get_all(self) -> List[InboxRecord]:
        with _lock:
            rows = self._read_raw()
        return [self._row_to_record(r) for r in rows]

    def get_active(self) -> List[InboxRecord]:
        return [r for r in self.get_all() if r.status == "active"]

    def find(self, email: str) -> Optional[InboxRecord]:
        for r in self.get_all():
            if r.email == email:
                return r
        return None

    def add(self, record: InboxRecord) -> None:
        with _lock:
            rows = self._read_raw()
            if any(r["email"] == record.email for r in rows):
                raise ValueError(f"Inbox {record.email!r} already exists.")
            rows.append(asdict(record))
            self._write_raw(rows)

    def update(self, record: InboxRecord) -> None:
        with _lock:
            rows = self._read_raw()
            updated = False
            for i, row in enumerate(rows):
                if row["email"] == record.email:
                    rows[i] = asdict(record)
                    updated = True
                    break
            if not updated:
                raise KeyError(f"Inbox {record.email!r} not found.")
            self._write_raw(rows)

    def delete(self, email: str) -> None:
        with _lock:
            rows = self._read_raw()
            rows = [r for r in rows if r["email"] != email]
            self._write_raw(rows)

    def pause(self, email: str, reason: str = "") -> None:
        record = self.find(email)
        if record:
            record.status = "paused"
            record.paused_reason = reason
            self.update(record)

    def resume(self, email: str) -> None:
        record = self.find(email)
        if record:
            record.status = "active"
            record.paused_reason = ""
            self.update(record)

    def increment_daily_sent(self, email: str) -> None:
        with _lock:
            rows = self._read_raw()
            for row in rows:
                if row["email"] == email:
                    row["daily_sent"] = int(row.get("daily_sent", 0)) + 1
                    row["last_sent_at"] = datetime.now().isoformat(timespec="seconds")
                    break
            self._write_raw(rows)

    def increment_daily_replied(self, email: str) -> None:
        """Track replies in last_sent_at field; extend schema if needed."""
        # Replies don't have a separate counter in the schema; we log via log_store.
        pass

    def reset_daily_counts(self) -> None:
        """Called at midnight by the scheduler."""
        with _lock:
            rows = self._read_raw()
            for row in rows:
                row["daily_sent"] = 0
            self._write_raw(rows)

    def update_stage(self, email: str, new_stage: int) -> None:
        from core.ramp_logic import STAGE_LIMITS
        record = self.find(email)
        if record:
            record.stage = new_stage
            record.daily_limit = STAGE_LIMITS.get(new_stage, 5)
            self.update(record)

    def mark_error(self, email: str, reason: str) -> None:
        record = self.find(email)
        if record:
            record.status = "error"
            record.paused_reason = reason
            self.update(record)
