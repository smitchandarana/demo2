"""
core/warmup_engine.py
Orchestrates warm-up email sending for all active inboxes.
Called by the APScheduler tick every 60 seconds.
Posts UI events to queue; never touches tkinter directly.
"""
import queue
import time
import logging
from datetime import datetime

from core.smtp_engine import SMTPEngine
from core.content_generator import generate_email
from core.ramp_logic import (
    get_daily_limit,
    should_send,
    within_working_hours,
    is_time_to_send,
    check_bounce_threshold,
    next_stage,
)
from core.logger import WarmupLogger
from storage.inbox_store import InboxStore, InboxRecord
from storage.recipient_store import RecipientStore
from storage.log_store import LogStore

logger = logging.getLogger("phoenix.warmup")

# Auto-pause threshold: consecutive SMTP errors before pausing inbox
MAX_CONSECUTIVE_ERRORS = 3


class WarmupEngine:
    """
    Main warm-up orchestrator.
    run_cycle() is called by the scheduler every tick.
    All SMTP network calls happen in the scheduler's background thread.
    """

    def __init__(
        self,
        inbox_store: InboxStore,
        recipient_store: RecipientStore,
        log_store: LogStore,
        ui_queue: queue.Queue,
    ) -> None:
        self.inbox_store = inbox_store
        self.recipient_store = recipient_store
        self.log_store = log_store
        self.ui_queue = ui_queue
        self._warmup_logger = WarmupLogger(log_store)

    # ------------------------------------------------------------------ #
    # Public scheduler entry point                                          #
    # ------------------------------------------------------------------ #

    def run_cycle(self) -> None:
        """
        Iterate all active inboxes. For each:
          1. Check working hours gate
          2. Check daily quota gate
          3. Check send interval gate
          4. Pick recipient and generate content
          5. Send via SMTP
          6. Update counters and logs
          7. Check safety thresholds (bounce rate, errors)
        """
        try:
            active = self.inbox_store.get_active()
        except Exception as exc:
            logger.error(f"Failed to load active inboxes: {exc}")
            return

        for inbox in active:
            try:
                self._process_inbox(inbox)
            except Exception as exc:
                logger.exception(f"Unhandled error for {inbox.email}: {exc}")
                self._post_ui("error", inbox.email,
                              f"Unexpected error: {exc}")

    # ------------------------------------------------------------------ #
    # Private: per-inbox processing                                         #
    # ------------------------------------------------------------------ #

    def _process_inbox(self, inbox: InboxRecord) -> None:
        """Process one send attempt for one inbox."""

        # --- Gate 1: Working hours ---
        if not within_working_hours(
            inbox.working_hours_start, inbox.working_hours_end
        ):
            return

        # --- Gate 2: Daily limit ---
        inbox_dict = {
            "daily_sent": inbox.daily_sent,
            "daily_limit": inbox.daily_limit,
        }
        if not should_send(inbox_dict):
            return

        # --- Gate 3: Send interval ---
        if not is_time_to_send(inbox.last_sent_at, inbox.stage):
            return

        # --- Pick recipient ---
        recipient = self.recipient_store.get_least_used(exclude_email=inbox.email)
        if recipient is None:
            logger.warning(f"No recipients available for {inbox.email}")
            self._post_ui("warning", inbox.email, "No recipients configured")
            return

        # --- Generate content ---
        content = generate_email(
            sender_name=inbox.email.split("@")[0].replace(".", " ").title(),
            recipient_name=recipient.name or recipient.email.split("@")[0],
        )

        # --- Send ---
        smtp = SMTPEngine(
            host=inbox.smtp_host,
            port=inbox.smtp_port,
            email=inbox.email,
            password=inbox.password,
        )

        result = smtp.send(
            to_email=recipient.email,
            to_name=recipient.name or "",
            subject=content.subject,
            body=content.body,
        )

        # Update recipient usage regardless of outcome
        try:
            self.recipient_store.record_use(recipient.email)
        except Exception:
            pass

        if result.success:
            self._handle_success(inbox, recipient.email, content.subject)
        else:
            self._handle_failure(inbox, recipient.email, result)

    # ------------------------------------------------------------------ #
    # Private: success / failure handling                                   #
    # ------------------------------------------------------------------ #

    def _handle_success(
        self, inbox: InboxRecord, to_email: str, subject: str
    ) -> None:
        """Update counters after a successful send."""
        new_sent = inbox.daily_sent + 1

        # Check for stage promotion
        new_stage = inbox.stage
        if new_sent >= inbox.daily_limit and inbox.stage < 4:
            # Full day quota met — advance stage on next reset
            # We advance stage immediately for simplicity
            new_stage = next_stage(inbox.stage)
            self._warmup_logger.stage_advance(inbox.email, inbox.stage, new_stage)
            self._post_ui(
                "stage_advance",
                inbox.email,
                f"Promoted to Stage {new_stage}! Daily limit now "
                f"{get_daily_limit(new_stage)}",
            )

        # Persist updates
        try:
            updated = InboxRecord(
                email=inbox.email,
                smtp_host=inbox.smtp_host,
                smtp_port=inbox.smtp_port,
                imap_host=inbox.imap_host,
                imap_port=inbox.imap_port,
                password=inbox.password,
                stage=new_stage,
                daily_sent=new_sent,
                daily_limit=get_daily_limit(new_stage),
                status=inbox.status,
                last_sent_at=datetime.now().isoformat(timespec="seconds"),
                paused_reason="",
                working_hours_start=inbox.working_hours_start,
                working_hours_end=inbox.working_hours_end,
            )
            self.inbox_store.update(updated)
        except Exception as exc:
            logger.error(f"Failed to update inbox after send: {exc}")

        # Log and notify UI
        self._warmup_logger.send(inbox.email, to_email, subject)
        self._post_ui(
            "send",
            inbox.email,
            f"Sent to {to_email} | {subject[:40]}",
        )

    def _handle_failure(self, inbox: InboxRecord, to_email: str, result) -> None:
        """Handle a failed send: log, check safety thresholds."""
        error_detail = result.error_message or "Unknown SMTP error"

        if result.is_auth_failure:
            self._warmup_logger.error(inbox.email, f"Auth failure: {error_detail}")
            self.inbox_store.mark_error(inbox.email, "Authentication failed")
            self._post_ui("error", inbox.email,
                          "Authentication failed — check credentials")
            return

        if result.is_hard_bounce:
            self._warmup_logger.bounce(inbox.email, to_email, error_detail)
            # Deactivate the bounced recipient
            try:
                self.recipient_store.deactivate(to_email)
            except Exception:
                pass
            # Check overall bounce rate
            bounces_24h = self.log_store.count_bounces_last_hours(inbox.email)
            sends_24h = self.log_store.count_sends_last_hours(inbox.email)
            inbox_dict = {
                "daily_sent": sends_24h,
                "bounced_today": bounces_24h,
            }
            if check_bounce_threshold(inbox_dict):
                self.inbox_store.pause(
                    inbox.email,
                    f"Auto-paused: bounce rate exceeded threshold",
                )
                self._warmup_logger.pause(inbox.email, "Bounce rate too high")
                self._post_ui("pause", inbox.email,
                              "Auto-paused: bounce rate exceeded 5%")
            else:
                self._post_ui("bounce", inbox.email,
                              f"Hard bounce from {to_email}")
            return

        if result.is_soft_bounce:
            self._warmup_logger.error(inbox.email, f"Soft bounce: {error_detail}")
            self._post_ui("error", inbox.email, f"Soft bounce: {error_detail[:60]}")
            return

        # Generic SMTP error
        self._warmup_logger.error(inbox.email, error_detail)
        self._post_ui("error", inbox.email, error_detail[:80])

    # ------------------------------------------------------------------ #
    # Private: UI queue                                                     #
    # ------------------------------------------------------------------ #

    def _post_ui(self, event_type: str, inbox_email: str, message: str) -> None:
        """
        Push event to UI queue non-blocking.
        Silently drops if queue is full.
        event_type: send | reply | bounce | error | pause | stage_advance | warning
        """
        try:
            self.ui_queue.put_nowait({
                "type": event_type,
                "inbox": inbox_email,
                "message": message,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            })
        except queue.Full:
            pass  # UI is slow; drop event rather than block
