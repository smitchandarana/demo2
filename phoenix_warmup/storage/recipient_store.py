"""
storage/recipient_store.py
Thread-safe CRUD for recipients.csv.
Recipients are the pool of addresses that warm-up emails are sent to/from.
"""
import csv
import threading
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import sys
import random


def _get_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent.parent
    d = base / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


CSV_PATH = _get_data_dir() / "recipients.csv"

HEADERS = ["email", "name", "domain", "active", "count_used", "last_used"]

_lock = threading.Lock()


@dataclass
class RecipientRecord:
    email: str
    name: str = ""
    domain: str = ""
    active: str = "true"     # stored as string in CSV
    count_used: int = 0
    last_used: str = ""

    def is_active(self) -> bool:
        return self.active.lower() == "true"

    def __post_init__(self):
        if isinstance(self.count_used, str):
            self.count_used = int(self.count_used) if self.count_used else 0


class RecipientStore:
    """Thread-safe CSV-backed store for warm-up recipient addresses."""

    def _ensure_file(self) -> None:
        if not CSV_PATH.exists():
            with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=HEADERS)
                writer.writeheader()

    def _read_raw(self) -> List[dict]:
        self._ensure_file()
        with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _write_raw(self, rows: List[dict]) -> None:
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerows(rows)

    def _row_to_record(self, row: dict) -> RecipientRecord:
        return RecipientRecord(
            email=row.get("email", ""),
            name=row.get("name", ""),
            domain=row.get("domain", ""),
            active=row.get("active", "true"),
            count_used=int(row.get("count_used", 0) or 0),
            last_used=row.get("last_used", ""),
        )

    def get_all(self) -> List[RecipientRecord]:
        with _lock:
            rows = self._read_raw()
        return [self._row_to_record(r) for r in rows]

    def get_active(self) -> List[RecipientRecord]:
        return [r for r in self.get_all() if r.is_active()]

    def has_records(self) -> bool:
        with _lock:
            rows = self._read_raw()
        return len(rows) > 0

    def get_least_used(self, exclude_email: str = "") -> Optional[RecipientRecord]:
        """Round-robin: pick active recipient with lowest usage count."""
        active = [r for r in self.get_active() if r.email != exclude_email]
        if not active:
            active = self.get_active()  # fallback: ignore exclusion
        if not active:
            return None
        # Sort by count_used ascending, then by last_used ascending for tie-breaking
        active.sort(key=lambda r: (r.count_used, r.last_used or ""))
        return active[0]

    def pick_random(self, exclude_email: str = "") -> Optional[RecipientRecord]:
        """Pick a random active recipient (weighted toward least used)."""
        active = [r for r in self.get_active() if r.email != exclude_email]
        if not active:
            active = self.get_active()
        if not active:
            return None
        return random.choice(active)

    def record_use(self, email: str) -> None:
        """Increment count_used and update last_used timestamp."""
        with _lock:
            rows = self._read_raw()
            for row in rows:
                if row["email"] == email:
                    row["count_used"] = str(int(row.get("count_used", 0) or 0) + 1)
                    row["last_used"] = datetime.now().isoformat(timespec="seconds")
                    break
            self._write_raw(rows)

    def add(self, record: RecipientRecord) -> None:
        with _lock:
            rows = self._read_raw()
            if any(r["email"] == record.email for r in rows):
                return  # Already exists - silently skip
            rows.append({
                "email": record.email,
                "name": record.name,
                "domain": record.domain,
                "active": record.active,
                "count_used": str(record.count_used),
                "last_used": record.last_used,
            })
            self._write_raw(rows)

    def delete(self, email: str) -> None:
        with _lock:
            rows = self._read_raw()
            rows = [r for r in rows if r["email"] != email]
            self._write_raw(rows)

    def deactivate(self, email: str) -> None:
        """Soft-delete: mark as inactive (used when emails bounce)."""
        with _lock:
            rows = self._read_raw()
            for row in rows:
                if row["email"] == email:
                    row["active"] = "false"
                    break
            self._write_raw(rows)

    def seed_with_faker(self, count: int = 100) -> None:
        """Generate synthetic recipient addresses using Faker."""
        try:
            from faker import Faker
            fake = Faker("en_US")
        except ImportError:
            return

        with _lock:
            existing = {r["email"] for r in self._read_raw()}
            new_rows = []
            attempts = 0
            while len(new_rows) < count and attempts < count * 3:
                attempts += 1
                first = fake.first_name().lower()
                last = fake.last_name().lower()
                domain = fake.domain_name()
                email = f"{first}.{last}@{domain}"
                if email not in existing:
                    existing.add(email)
                    new_rows.append({
                        "email": email,
                        "name": f"{fake.first_name()} {fake.last_name()}",
                        "domain": domain,
                        "active": "true",
                        "count_used": "0",
                        "last_used": "",
                    })

            rows = self._read_raw()
            rows.extend(new_rows)
            self._write_raw(rows)
