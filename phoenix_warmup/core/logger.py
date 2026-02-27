"""
core/logger.py
Thin facade over LogStore for structured event logging.
Never logs passwords or sensitive credentials.
"""
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from storage.log_store import LogStore, LogRecord


class WarmupLogger:
    """
    Wraps LogStore with typed log methods.
    All methods are safe to call from background threads
    (LogStore itself is thread-safe via threading.Lock).
    """

    def __init__(self, log_store: "LogStore") -> None:
        self._store = log_store

    def _write(
        self,
        inbox_email: str,
        event_type: str,
        recipient: str = "",
        subject: str = "",
        details: str = "",
    ) -> None:
        from storage.log_store import LogRecord
        record = LogRecord(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            inbox_email=inbox_email,
            event_type=event_type,
            recipient=recipient,
            subject=subject,
            details=details,
        )
        try:
            self._store.append(record)
        except Exception as exc:
            # Logging must never crash the caller
            print(f"[WarmupLogger] Failed to write log: {exc}")

    def send(self, inbox_email: str, recipient: str, subject: str) -> None:
        self._write(inbox_email, "SEND", recipient=recipient, subject=subject,
                    details="OK")

    def reply(self, inbox_email: str, recipient: str, subject: str) -> None:
        self._write(inbox_email, "REPLY", recipient=recipient, subject=subject,
                    details="OK")

    def bounce(self, inbox_email: str, recipient: str, details: str = "") -> None:
        self._write(inbox_email, "BOUNCE", recipient=recipient,
                    details=details)

    def error(self, inbox_email: str, details: str) -> None:
        # Sanitize: never include passwords in logs
        safe = _redact_passwords(details)
        self._write(inbox_email, "ERROR", details=safe)

    def pause(self, inbox_email: str, reason: str) -> None:
        self._write(inbox_email, "PAUSE", details=reason)

    def resume(self, inbox_email: str) -> None:
        self._write(inbox_email, "RESUME", details="Manually resumed")

    def stage_advance(self, inbox_email: str, old_stage: int, new_stage: int) -> None:
        self._write(inbox_email, "STAGE",
                    details=f"Stage {old_stage} → {new_stage}")

    def reset(self, inbox_email: str) -> None:
        self._write(inbox_email, "RESET", details="Daily counters reset")

    def info(self, inbox_email: str, details: str) -> None:
        self._write(inbox_email, "INFO", details=details)


def _redact_passwords(text: str) -> str:
    """Remove common password-like patterns from log strings."""
    import re
    # Redact anything that looks like password=<value>
    text = re.sub(
        r"(password|passwd|pass|pwd)\s*[=:]\s*\S+",
        r"\1=***",
        text,
        flags=re.IGNORECASE,
    )
    return text
