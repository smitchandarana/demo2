"""
storage/inbox_store.py
Thread-safe CRUD operations for inboxes.csv.
Uses a module-level threading.Lock to prevent concurrent write corruption.
"""
import csv
import threading
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Resolve data directory (PyInstaller-safe)
import sys

def _get_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        # Use the directory containing the .exe, not the read-only _MEIPASS bundle
        base = Path(sys.executable).parent
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
    "display_name",  # Added after initial release; old rows default to ""
]

_lock = threading.Lock()

# Imported here to avoid a circular import (core does not import storage).
from core.ramp_logic import STAGE_LIMITS  # noqa: E402


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
    display_name: str = ""

    def __post_init__(self):
        # Safely coerce CSV string values to int with fallback defaults.
        # int("") raises ValueError, so guard against empty/missing columns.
        def _int(v, default: int) -> int:
            try:
                return int(v)
            except (ValueError, TypeError):
                return default

        self.smtp_port  = _int(self.smtp_port,  587)
        self.imap_port  = _int(self.imap_port,  993)
        self.stage      = _int(self.stage,       1)
        self.daily_sent = _int(self.daily_sent,  0)
        self.daily_limit= _int(self.daily_limit, 5)


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
        """Atomically set inbox status to paused within a single lock."""
        with _lock:
            rows = self._read_raw()
            for row in rows:
                if row["email"] == email:
                    row["status"] = "paused"
                    row["paused_reason"] = reason
                    break
            self._write_raw(rows)

    def resume(self, email: str) -> None:
        """Atomically set inbox status back to active within a single lock."""
        with _lock:
            rows = self._read_raw()
            for row in rows:
                if row["email"] == email:
                    row["status"] = "active"
                    row["paused_reason"] = ""
                    break
            self._write_raw(rows)

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
        """Called at midnight by the scheduler. Resets sent counter and
        recalculates daily_limit from the current stage so stage advances
        take effect at the start of the new day."""
        with _lock:
            rows = self._read_raw()
            for row in rows:
                row["daily_sent"] = "0"
                stage = int(row.get("stage", "1") or "1")
                row["daily_limit"] = str(STAGE_LIMITS.get(stage, 5))
            self._write_raw(rows)

    def update_stage(self, email: str, new_stage: int) -> None:
        """Atomically update stage and daily_limit within a single lock."""
        with _lock:
            rows = self._read_raw()
            for row in rows:
                if row["email"] == email:
                    row["stage"] = str(new_stage)
                    row["daily_limit"] = str(STAGE_LIMITS.get(new_stage, 5))
                    break
            self._write_raw(rows)

    def mark_error(self, email: str, reason: str) -> None:
        """Atomically mark inbox as errored within a single lock."""
        with _lock:
            rows = self._read_raw()
            for row in rows:
                if row["email"] == email:
                    row["status"] = "error"
                    row["paused_reason"] = reason
                    break
            self._write_raw(rows)
