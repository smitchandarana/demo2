"""
storage/log_store.py
Append-only thread-safe CSV log store.
Rows are never deleted; only appended or queried.
"""
import csv
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
import sys


def _get_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent.parent
    d = base / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


CSV_PATH = _get_data_dir() / "logs.csv"

HEADERS = [
    "timestamp", "inbox_email", "event_type",
    "recipient", "subject", "details",
]

_lock = threading.Lock()


@dataclass
class LogRecord:
    timestamp: str
    inbox_email: str
    event_type: str          # SEND | REPLY | BOUNCE | ERROR | PAUSE | RESET | STAGE
    recipient: str = ""
    subject: str = ""
    details: str = ""

    @classmethod
    def now(cls, inbox_email: str, event_type: str, **kwargs) -> "LogRecord":
        return cls(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            inbox_email=inbox_email,
            event_type=event_type,
            **kwargs,
        )


class LogStore:
    """Append-only CSV log. Thread-safe via threading.Lock."""

    def _ensure_file(self) -> None:
        if not CSV_PATH.exists():
            with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=HEADERS)
                writer.writeheader()

    def append(self, record: LogRecord) -> None:
        with _lock:
            self._ensure_file()
            file_empty = CSV_PATH.stat().st_size == 0
            with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=HEADERS)
                if file_empty:
                    writer.writeheader()
                writer.writerow(asdict(record))

    def get_recent(self, n: int = 200) -> List[LogRecord]:
        with _lock:
            self._ensure_file()
            with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        return [self._row_to_record(r) for r in rows[-n:]]

    def get_today_stats(self) -> dict:
        """Return totals for SEND, REPLY, ERROR events today."""
        today = datetime.now().date().isoformat()
        stats = {"sends": 0, "replies": 0, "errors": 0, "bounces": 0}
        with _lock:
            self._ensure_file()
            with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if row.get("timestamp", "").startswith(today):
                        et = row.get("event_type", "")
                        if et == "SEND":
                            stats["sends"] += 1
                        elif et == "REPLY":
                            stats["replies"] += 1
                        elif et == "ERROR":
                            stats["errors"] += 1
                        elif et == "BOUNCE":
                            stats["bounces"] += 1
        return stats

    def count_bounces_last_hours(self, inbox_email: str, hours: int = 24) -> int:
        """Count hard bounces for a specific inbox in the last N hours."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        count = 0
        with _lock:
            self._ensure_file()
            with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if (row.get("inbox_email") == inbox_email
                            and row.get("event_type") == "BOUNCE"
                            and row.get("timestamp", "") >= cutoff):
                        count += 1
        return count

    def count_sends_last_hours(self, inbox_email: str, hours: int = 24) -> int:
        """Count successful sends for a specific inbox in the last N hours."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        count = 0
        with _lock:
            self._ensure_file()
            with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if (row.get("inbox_email") == inbox_email
                            and row.get("event_type") == "SEND"
                            and row.get("timestamp", "") >= cutoff):
                        count += 1
        return count

    def _row_to_record(self, row: dict) -> LogRecord:
        return LogRecord(
            timestamp=row.get("timestamp", ""),
            inbox_email=row.get("inbox_email", ""),
            event_type=row.get("event_type", ""),
            recipient=row.get("recipient", ""),
            subject=row.get("subject", ""),
            details=row.get("details", ""),
        )
