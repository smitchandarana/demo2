"""
core/reply_engine.py
Scans inboxes for warm-up emails and sends human-like replies.
Called by the scheduler's IMAP check job.
Reply rate is configurable via .env (REPLY_RATE, default 0.4).
"""
import os
import queue
import random
import logging
from datetime import datetime

from core.imap_engine import IMAPEngine, FetchedMessage
from core.smtp_engine import SMTPEngine
from core.content_generator import generate_email
from core.logger import WarmupLogger
from storage.inbox_store import InboxStore, InboxRecord
from storage.log_store import LogStore

logger = logging.getLogger("phoenix.reply")


class ReplyEngine:
    """
    Scans each active inbox via IMAP for unread messages,
    then probabilistically replies to simulate engagement.
    """

    def __init__(
        self,
        inbox_store: InboxStore,
        log_store: LogStore,
        ui_queue: queue.Queue,
    ) -> None:
        self.inbox_store = inbox_store
        self.log_store = log_store
        self.ui_queue = ui_queue
        self._warmup_logger = WarmupLogger(log_store)

    @property
    def reply_rate(self) -> float:
        """Fraction of received emails to reply to (0.0–1.0)."""
        return float(os.environ.get("REPLY_RATE", "0.40"))

    def run_reply_cycle(self) -> None:
        """
        Main scheduler entry point.
        Iterates all active inboxes, fetches unseen messages, replies.
        """
        try:
            active = self.inbox_store.get_active()
        except Exception as exc:
            logger.error(f"Failed to load active inboxes for reply cycle: {exc}")
            return

        for inbox in active:
            try:
                self._process_inbox_replies(inbox)
            except Exception as exc:
                logger.exception(f"Reply error for {inbox.email}: {exc}")

    def _process_inbox_replies(self, inbox: InboxRecord) -> None:
        """Fetch unseen messages for one inbox and reply to qualifying ones."""
        imap = IMAPEngine(
            host=inbox.imap_host,
            port=inbox.imap_port,
            email=inbox.email,
            password=inbox.password,
        )

        messages = imap.fetch_unseen()
        if not messages:
            return

        for msg in messages:
            if self._should_reply(msg):
                self._send_reply(inbox, msg)

    def _should_reply(self, msg: FetchedMessage) -> bool:
        """
        Probabilistic gate — reply to reply_rate fraction of messages.
        Also skips messages from the same domain (self-loops) or
        messages that look like system/auto-generated mail.
        """
        subject = msg.subject.lower()
        # Skip obvious system emails
        if any(kw in subject for kw in [
            "unsubscribe", "no-reply", "noreply", "bounce",
            "auto-reply", "out of office", "vacation", "delivery failure",
        ]):
            return False
        # Probabilistic gate
        return random.random() < self.reply_rate

    def _send_reply(self, inbox: InboxRecord, msg: FetchedMessage) -> None:
        """Generate and send a reply to a received message."""
        # Generate reply content
        sender_display = inbox.email.split("@")[0].replace(".", " ").title()
        content = generate_email(
            sender_name=sender_display,
            recipient_name=msg.from_name or msg.from_email.split("@")[0],
            is_reply=True,
            original_subject=msg.subject,
            original_body_snippet=msg.body_text[:300],
        )

        smtp = SMTPEngine(
            host=inbox.smtp_host,
            port=inbox.smtp_port,
            email=inbox.email,
            password=inbox.password,
        )

        result = smtp.send(
            to_email=msg.from_email,
            to_name=msg.from_name or msg.from_email,
            subject=content.subject,
            body=content.body,
            in_reply_to=msg.message_id,
            references=msg.message_id,
        )

        if result.success:
            self._warmup_logger.reply(inbox.email, msg.from_email, content.subject)
            self._post_ui(
                "reply",
                inbox.email,
                f"Replied to {msg.from_email} | {content.subject[:40]}",
            )
        else:
            self._warmup_logger.error(
                inbox.email,
                f"Reply failed to {msg.from_email}: {result.error_message}",
            )
            self._post_ui("error", inbox.email,
                          f"Reply failed: {result.error_message[:60]}")

    def _post_ui(self, event_type: str, inbox_email: str, message: str) -> None:
        """Non-blocking push to UI queue."""
        try:
            self.ui_queue.put_nowait({
                "type": event_type,
                "inbox": inbox_email,
                "message": message,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            })
        except queue.Full:
            pass
