"""
app.py
Central application assembler for Phoenix Warm-Up Engine.
Instantiates all stores, engines, scheduler, and the dashboard.
Wires them together via a shared queue.Queue for thread-safe UI updates.
"""
import queue
import sys
from pathlib import Path

from storage.inbox_store import InboxStore
from storage.recipient_store import RecipientStore
from storage.log_store import LogStore
from core.warmup_engine import WarmupEngine
from core.reply_engine import ReplyEngine
from scheduler import WarmupScheduler
from ui.dashboard import Dashboard


class App:
    """
    Top-level application object.
    Owns all singletons and wires them together.
    Call run() to start the event loop.
    """

    def __init__(self, data_dir: Path, assets_dir: Path) -> None:
        self.data_dir = data_dir
        self.assets_dir = assets_dir

        # Thread-safe event queue: background threads → UI main thread
        self.ui_queue: queue.Queue = queue.Queue(maxsize=1000)

        # ── Storage Layer ──────────────────────────────────────────────── #
        self.inbox_store = InboxStore()
        self.recipient_store = RecipientStore()
        self.log_store = LogStore()

        # Seed recipients on first run
        if not self.recipient_store.has_records():
            self._seed_recipients()

        # ── Core Engines ───────────────────────────────────────────────── #
        self.warmup_engine = WarmupEngine(
            inbox_store=self.inbox_store,
            recipient_store=self.recipient_store,
            log_store=self.log_store,
            ui_queue=self.ui_queue,
        )

        self.reply_engine = ReplyEngine(
            inbox_store=self.inbox_store,
            log_store=self.log_store,
            ui_queue=self.ui_queue,
        )

        # ── Scheduler ─────────────────────────────────────────────────── #
        self.scheduler = WarmupScheduler(
            warmup_engine=self.warmup_engine,
            reply_engine=self.reply_engine,
            inbox_store=self.inbox_store,
            ui_queue=self.ui_queue,
        )

        # ── Dashboard (owns the tkinter root window) ───────────────────── #
        self.dashboard = Dashboard(
            inbox_store=self.inbox_store,
            recipient_store=self.recipient_store,
            log_store=self.log_store,
            scheduler=self.scheduler,
            ui_queue=self.ui_queue,
            assets_dir=self.assets_dir,
        )

    def _seed_recipients(self) -> None:
        """Generate initial pool of fake recipients on first startup."""
        try:
            self.recipient_store.seed_with_faker(count=150)
        except Exception as exc:
            print(f"[App] Warning: Could not seed recipients: {exc}")

    def run(self) -> None:
        """Start the tkinter main loop. Blocks until window is closed."""
        self.dashboard.mainloop()
        # When mainloop returns, dashboard has already shut down the scheduler
