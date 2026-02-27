"""
ui/dashboard.py
Phoenix Warm-Up Engine — Full CustomTkinter Dashboard
Phoenix Solutions © 2024

Layout:
  ┌─────────────────────────────────────────────────────────┐
  │  HEADER  (logo | title | status badge | start/stop)     │
  ├────────────────────────────┬────────────────────────────┤
  │  LEFT PANEL (60%)          │  RIGHT PANEL (40%)         │
  │  ┌── Stat Cards ──────────┐│  ┌── Activity Feed ───────┐│
  │  └────────────────────────┘│  └────────────────────────┘│
  │  ┌── Inbox Management ────┐│                            │
  │  │  [table rows]          ││                            │
  │  │  [Add / Pause / Del]   ││                            │
  │  └────────────────────────┘│                            │
  ├────────────────────────────┴────────────────────────────┤
  │  STATUS BAR  (next cycle | version)                     │
  └─────────────────────────────────────────────────────────┘
"""
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

try:
    import customtkinter as ctk
    from customtkinter import CTkImage
    _CTK_AVAILABLE = True
except ImportError:
    import tkinter as tk
    import tkinter.ttk as ttk
    _CTK_AVAILABLE = False

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

from storage.inbox_store import InboxStore, InboxRecord
from storage.recipient_store import RecipientStore, RecipientRecord
from storage.log_store import LogStore
from core.ramp_logic import get_daily_limit

# ── Brand colors ──────────────────────────────────────────────────────────── #
PRIMARY     = "#FF6A00"   # Deep orange
SECONDARY   = "#1E1E1E"   # Dark charcoal
BG          = "#2B2B2B"   # Dark background
BG_CARD     = "#3A3A3A"   # Card background
ACCENT      = "#FFFFFF"   # White text
MUTED       = "#AAAAAA"   # Muted text
SUCCESS     = "#4CAF50"   # Green
WARNING     = "#FF9800"   # Orange
ERROR_COLOR = "#F44336"   # Red
REPLY_CLR   = "#2196F3"   # Blue

STAGE_COLORS = {1: "#64B5F6", 2: "#4DB6AC", 3: "#81C784", 4: "#FF6A00"}

POLL_INTERVAL_MS = 500   # Queue poll frequency
MAX_FEED_ROWS    = 50    # Max activity feed rows to keep

EVENT_ICONS = {
    "send":          ("↑ SEND",   PRIMARY),
    "reply":         ("↩ REPLY",  REPLY_CLR),
    "bounce":        ("✗ BOUNCE", ERROR_COLOR),
    "error":         ("⚠ ERROR",  ERROR_COLOR),
    "pause":         ("⏸ PAUSE",  WARNING),
    "resume":        ("▶ RESUME", SUCCESS),
    "stage_advance": ("★ STAGE",  PRIMARY),
    "warning":       ("⚠ WARN",   WARNING),
    "status":        ("● SYS",    MUTED),
}


def _setup_ctk() -> None:
    """Configure CustomTkinter global appearance."""
    if _CTK_AVAILABLE:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")


class Dashboard(ctk.CTk if _CTK_AVAILABLE else object):
    """
    Main application window.
    Inherits from CTk (the root window) so we call self.mainloop() directly.
    """

    def __init__(
        self,
        inbox_store: InboxStore,
        recipient_store: RecipientStore,
        log_store: LogStore,
        scheduler,
        ui_queue: queue.Queue,
        assets_dir: Path,
    ) -> None:
        _setup_ctk()
        super().__init__()

        self.inbox_store = inbox_store
        self.recipient_store = recipient_store
        self.log_store = log_store
        self.scheduler = scheduler
        self.ui_queue = ui_queue
        self.assets_dir = assets_dir

        # Internal state
        self._feed_rows: List = []
        self._inbox_row_widgets: Dict[str, dict] = {}
        self._selected_inbox: Optional[str] = None

        # Window setup
        self.title("Phoenix Warm-Up Engine — by Phoenix Solutions")
        self.geometry("1280x800")
        self.minsize(1100, 680)
        self.configure(fg_color=SECONDARY)

        self._build_ui()
        self._load_logo()
        self._refresh_inbox_table()
        self._refresh_stats()

        # Start polling the UI event queue
        self.after(POLL_INTERVAL_MS, self._poll_queue)

        # Graceful close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ================================================================== #
    #  UI Build                                                            #
    # ================================================================== #

    def _build_ui(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_main_content()
        self._build_status_bar()

    def _build_header(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color=SECONDARY, height=64, corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(2, weight=1)
        hdr.grid_propagate(False)

        # Logo placeholder label
        self._logo_label = ctk.CTkLabel(
            hdr, text="🔥", font=ctk.CTkFont(size=28), text_color=PRIMARY,
        )
        self._logo_label.grid(row=0, column=0, padx=(16, 4), pady=12)

        # App title
        title_lbl = ctk.CTkLabel(
            hdr,
            text="Phoenix Warm-Up Engine",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=PRIMARY,
        )
        title_lbl.grid(row=0, column=1, padx=(0, 16), pady=12, sticky="w")

        subtitle = ctk.CTkLabel(
            hdr, text="by Phoenix Solutions",
            font=ctk.CTkFont(size=11), text_color=MUTED,
        )
        subtitle.grid(row=0, column=2, padx=0, pady=20, sticky="w")

        # Status badge
        self._status_badge = ctk.CTkLabel(
            hdr,
            text="● Stopped",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=WARNING,
        )
        self._status_badge.grid(row=0, column=3, padx=16)

        # Start / Stop buttons
        btn_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_frame.grid(row=0, column=4, padx=16, pady=8)

        self._start_btn = ctk.CTkButton(
            btn_frame, text="▶  Start",
            fg_color=SUCCESS, hover_color="#388E3C",
            font=ctk.CTkFont(weight="bold"),
            width=100, command=self._on_start,
        )
        self._start_btn.grid(row=0, column=0, padx=(0, 6))

        self._stop_btn = ctk.CTkButton(
            btn_frame, text="■  Stop",
            fg_color=ERROR_COLOR, hover_color="#C62828",
            font=ctk.CTkFont(weight="bold"),
            width=100, command=self._on_stop, state="disabled",
        )
        self._stop_btn.grid(row=0, column=1)

    def _build_main_content(self) -> None:
        main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        main.grid(row=1, column=0, sticky="nsew")
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=3)   # Left: 60%
        main.grid_columnconfigure(1, weight=2)   # Right: 40%

        self._build_left_panel(main)
        self._build_right_panel(main)

    def _build_left_panel(self, parent) -> None:
        left = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        self._build_stat_cards(left)
        self._build_inbox_table(left)
        self._build_inbox_toolbar(left)
        self._build_controls(left)

    def _build_stat_cards(self, parent) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        row.grid_columnconfigure((0, 1, 2, 3), weight=1)

        stats_def = [
            ("Inboxes", "0", "total"),
            ("Sent Today", "0", "sends"),
            ("Replies", "0", "replies"),
            ("Bounces", "0", "bounces"),
        ]
        self._stat_labels: Dict[str, ctk.CTkLabel] = {}

        for i, (label, default, key) in enumerate(stats_def):
            card = ctk.CTkFrame(row, fg_color=BG_CARD, corner_radius=10)
            card.grid(row=0, column=i, padx=4, pady=2, sticky="ew")
            card.grid_columnconfigure(0, weight=1)

            val_lbl = ctk.CTkLabel(
                card, text=default,
                font=ctk.CTkFont(size=28, weight="bold"),
                text_color=PRIMARY,
            )
            val_lbl.grid(row=0, column=0, pady=(10, 0))

            ctk.CTkLabel(
                card, text=label,
                font=ctk.CTkFont(size=11), text_color=MUTED,
            ).grid(row=1, column=0, pady=(0, 10))

            self._stat_labels[key] = val_lbl

    def _build_inbox_table(self, parent) -> None:
        # Header row
        hdr = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=8)
        hdr.grid(row=1, column=0, sticky="ew", pady=(0, 2))
        for col, (text, w) in enumerate([
            ("Email Address", 220), ("Stage", 60),
            ("Sent/Limit", 90), ("Status", 80), ("Last Sent", 120)
        ]):
            ctk.CTkLabel(
                hdr, text=text,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=MUTED, width=w, anchor="w",
            ).grid(row=0, column=col, padx=8, pady=6, sticky="w")

        # Scrollable table body
        self._inbox_scroll = ctk.CTkScrollableFrame(
            parent, fg_color=SECONDARY, corner_radius=8,
        )
        self._inbox_scroll.grid(row=2, column=0, sticky="nsew", pady=(0, 4))
        self._inbox_scroll.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

    def _build_inbox_toolbar(self, parent) -> None:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", pady=(0, 6))

        ctk.CTkButton(
            bar, text="+ Add Inbox",
            fg_color=PRIMARY, hover_color="#CC5500",
            width=110, command=self._on_add_inbox,
        ).grid(row=0, column=0, padx=(0, 6))

        ctk.CTkButton(
            bar, text="✎ Edit Stage",
            fg_color=BG_CARD, hover_color="#555555",
            width=100, command=self._on_edit_stage,
        ).grid(row=0, column=1, padx=(0, 6))

        self._pause_btn = ctk.CTkButton(
            bar, text="⏸ Pause",
            fg_color=BG_CARD, hover_color="#555555",
            width=90, command=self._on_pause_inbox,
        )
        self._pause_btn.grid(row=0, column=2, padx=(0, 6))

        ctk.CTkButton(
            bar, text="✖ Delete",
            fg_color="#8B0000", hover_color="#5C0000",
            width=90, command=self._on_delete_inbox,
        ).grid(row=0, column=3)

        ctk.CTkButton(
            bar, text="↺ Reset Counters",
            fg_color=BG_CARD, hover_color="#555555",
            width=130, command=self._on_reset_counters,
        ).grid(row=0, column=4, padx=(16, 0))

    def _build_controls(self, parent) -> None:
        ctrl = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=8)
        ctrl.grid(row=4, column=0, sticky="ew", pady=(4, 0))
        ctrl.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(
            ctrl, text="System Status:",
            font=ctk.CTkFont(weight="bold"), text_color=MUTED,
        ).grid(row=0, column=0, padx=10, pady=8, sticky="w")

        self._system_status_lbl = ctk.CTkLabel(
            ctrl, text="Stopped",
            font=ctk.CTkFont(weight="bold"), text_color=WARNING,
        )
        self._system_status_lbl.grid(row=0, column=1, sticky="w")

        self._next_cycle_lbl = ctk.CTkLabel(
            ctrl, text="Next cycle: --",
            font=ctk.CTkFont(size=11), text_color=MUTED,
        )
        self._next_cycle_lbl.grid(row=0, column=2, padx=10)

        ctk.CTkButton(
            ctrl, text="+ Add Recipients",
            fg_color=BG, hover_color="#4A4A4A", width=130,
            command=self._on_add_recipients_dialog,
        ).grid(row=0, column=3, padx=10, pady=6)

    def _build_right_panel(self, parent) -> None:
        right = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right,
            text="Live Activity Feed",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=4, pady=(0, 4))

        self._feed_frame = ctk.CTkScrollableFrame(
            right, fg_color=SECONDARY, corner_radius=8, label_text="",
        )
        self._feed_frame.grid(row=1, column=0, sticky="nsew")

    def _build_status_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=SECONDARY, height=28, corner_radius=0)
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)
        bar.grid_propagate(False)

        self._statusbar_msg = ctk.CTkLabel(
            bar, text="", font=ctk.CTkFont(size=10), text_color=MUTED,
        )
        self._statusbar_msg.grid(row=0, column=0, padx=16, sticky="w")

        ctk.CTkLabel(
            bar,
            text="Phoenix Warm-Up Engine v1.0.0 | Phoenix Solutions",
            font=ctk.CTkFont(size=10), text_color=MUTED,
        ).grid(row=0, column=2, padx=16, sticky="e")

    # ================================================================== #
    #  Logo Loading                                                        #
    # ================================================================== #

    def _load_logo(self) -> None:
        """Load phoenix_logo.png from assets/ dir, or keep emoji fallback."""
        if not _PIL_AVAILABLE or not _CTK_AVAILABLE:
            return
        logo_path = self.assets_dir / "phoenix_logo.png"
        if logo_path.exists():
            try:
                pil_img = Image.open(logo_path).resize((40, 40))
                ctk_img = CTkImage(pil_img, size=(40, 40))
                self._logo_label.configure(image=ctk_img, text="")
                self._logo_label._image = ctk_img  # keep reference
            except Exception:
                pass  # Keep emoji fallback

    # ================================================================== #
    #  Inbox Table Rendering                                               #
    # ================================================================== #

    def _refresh_inbox_table(self) -> None:
        """Clear and re-render all inbox rows from store."""
        # Destroy tracked row frames directly.
        # winfo_children() on CTkScrollableFrame returns its internal canvas/
        # scrollbars — not our custom frames — so we must use our own dict.
        for widgets in list(self._inbox_row_widgets.values()):
            try:
                widgets["frame"].destroy()
            except Exception:
                pass
        self._inbox_row_widgets.clear()

        inboxes = self.inbox_store.get_all()
        if not inboxes:
            ctk.CTkLabel(
                self._inbox_scroll,
                text="No inboxes yet. Click '+ Add Inbox' to get started.",
                text_color=MUTED, font=ctk.CTkFont(size=12),
            ).grid(row=0, column=0, pady=20, padx=20)
            return

        for i, inbox in enumerate(inboxes):
            self._render_inbox_row(i, inbox)

        # Update stat cards after refresh
        self._refresh_stats()

    def _render_inbox_row(self, row_idx: int, inbox: InboxRecord) -> None:
        """Render one inbox row into the scrollable frame."""
        bg = BG_CARD if row_idx % 2 == 0 else "#333333"

        row_frame = ctk.CTkFrame(
            self._inbox_scroll, fg_color=bg, corner_radius=4,
        )
        row_frame.grid(row=row_idx, column=0, sticky="ew", pady=1, padx=2)
        row_frame.grid_columnconfigure(0, weight=1)

        # Make row clickable for selection
        row_frame.bind("<Button-1>", lambda e, em=inbox.email: self._select_inbox(em))

        # Email
        email_lbl = ctk.CTkLabel(
            row_frame, text=inbox.email,
            font=ctk.CTkFont(size=12), text_color=ACCENT,
            anchor="w", width=220,
        )
        email_lbl.grid(row=0, column=0, padx=8, pady=6, sticky="w")
        email_lbl.bind("<Button-1>", lambda e, em=inbox.email: self._select_inbox(em))

        # Stage badge
        stage_color = STAGE_COLORS.get(inbox.stage, MUTED)
        stage_lbl = ctk.CTkLabel(
            row_frame,
            text=f"S{inbox.stage}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=stage_color, width=50,
        )
        stage_lbl.grid(row=0, column=1, padx=4)

        # Sent / Limit
        limit = inbox.daily_limit or get_daily_limit(inbox.stage)
        sent_lbl = ctk.CTkLabel(
            row_frame,
            text=f"{inbox.daily_sent}/{limit}",
            font=ctk.CTkFont(size=11), text_color=MUTED, width=80,
        )
        sent_lbl.grid(row=0, column=2, padx=4)

        # Status
        status_color = {
            "active": SUCCESS, "paused": WARNING, "error": ERROR_COLOR,
        }.get(inbox.status, MUTED)
        status_lbl = ctk.CTkLabel(
            row_frame,
            text=inbox.status.capitalize(),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=status_color, width=70,
        )
        status_lbl.grid(row=0, column=3, padx=4)

        # Last sent
        last = inbox.last_sent_at[:16] if inbox.last_sent_at else "—"
        last_lbl = ctk.CTkLabel(
            row_frame, text=last,
            font=ctk.CTkFont(size=10), text_color=MUTED, width=110,
        )
        last_lbl.grid(row=0, column=4, padx=4)

        self._inbox_row_widgets[inbox.email] = {
            "frame": row_frame,
            "stage": stage_lbl,
            "sent": sent_lbl,
            "status": status_lbl,
            "last": last_lbl,
        }

    def _update_inbox_row(self, email: str) -> None:
        """Refresh a single row after an event (without full table rebuild)."""
        inbox = self.inbox_store.find(email)
        if not inbox or email not in self._inbox_row_widgets:
            self._refresh_inbox_table()
            return

        w = self._inbox_row_widgets[email]
        stage_color = STAGE_COLORS.get(inbox.stage, MUTED)
        w["stage"].configure(text=f"S{inbox.stage}", text_color=stage_color)

        limit = inbox.daily_limit or get_daily_limit(inbox.stage)
        w["sent"].configure(text=f"{inbox.daily_sent}/{limit}")

        status_color = {
            "active": SUCCESS, "paused": WARNING, "error": ERROR_COLOR,
        }.get(inbox.status, MUTED)
        w["status"].configure(text=inbox.status.capitalize(),
                              text_color=status_color)

        last = inbox.last_sent_at[:16] if inbox.last_sent_at else "—"
        w["last"].configure(text=last)

    def _select_inbox(self, email: str) -> None:
        """Highlight the selected inbox row."""
        self._selected_inbox = email
        for em, widgets in self._inbox_row_widgets.items():
            color = PRIMARY if em == email else "transparent"
            widgets["frame"].configure(border_color=color, border_width=1)

    # ================================================================== #
    #  Stats Cards                                                         #
    # ================================================================== #

    def _refresh_stats(self) -> None:
        """Update the summary stat cards."""
        all_inboxes = self.inbox_store.get_all()
        self._stat_labels["total"].configure(text=str(len(all_inboxes)))

        stats = self.log_store.get_today_stats()
        self._stat_labels["sends"].configure(text=str(stats["sends"]))
        self._stat_labels["replies"].configure(text=str(stats["replies"]))
        self._stat_labels["bounces"].configure(text=str(stats["bounces"]))

    # ================================================================== #
    #  Activity Feed                                                       #
    # ================================================================== #

    def _push_feed_event(self, event: dict) -> None:
        """Add one row to the live activity feed (called from main thread)."""
        icon_text, icon_color = EVENT_ICONS.get(
            event.get("type", ""), ("• INFO", MUTED)
        )
        ts = event.get("timestamp", datetime.now().strftime("%H:%M:%S"))
        inbox = event.get("inbox", "")
        message = event.get("message", "")

        text = f"{ts}  {icon_text:<12}  {inbox:<30}  {message}"

        lbl = ctk.CTkLabel(
            self._feed_frame,
            text=text,
            font=ctk.CTkFont(family="Courier", size=11),
            text_color=icon_color,
            anchor="w",
        )
        lbl.grid(sticky="ew", padx=4, pady=1)
        self._feed_rows.append(lbl)

        # Trim old rows
        if len(self._feed_rows) > MAX_FEED_ROWS:
            oldest = self._feed_rows.pop(0)
            oldest.destroy()

    # ================================================================== #
    #  Queue Polling                                                        #
    # ================================================================== #

    def _poll_queue(self) -> None:
        """
        Called every POLL_INTERVAL_MS via tkinter after().
        Drains all pending events and updates UI accordingly.
        """
        try:
            # Process up to 20 events per poll to avoid blocking
            for _ in range(20):
                event = self.ui_queue.get_nowait()
                self._dispatch_event(event)
        except queue.Empty:
            pass
        finally:
            self.after(POLL_INTERVAL_MS, self._poll_queue)

    def _dispatch_event(self, event: dict) -> None:
        """Route an event dict to the appropriate UI update."""
        self._push_feed_event(event)

        event_type = event.get("type", "")
        inbox_email = event.get("inbox", "")

        if event_type in ("send", "reply", "bounce", "error", "stage_advance"):
            if inbox_email and inbox_email != "system":
                self._update_inbox_row(inbox_email)
            self._refresh_stats()

        elif event_type == "pause":
            if inbox_email:
                self._update_inbox_row(inbox_email)
            self._set_statusbar(
                f"⏸ {inbox_email} auto-paused: {event.get('message', '')}"
            )

        elif event_type == "status":
            running = self.scheduler.is_running()
            self._update_running_state(running)

    # ================================================================== #
    #  Button Handlers                                                     #
    # ================================================================== #

    def _on_start(self) -> None:
        self.scheduler.start()
        self._update_running_state(True)
        self._push_feed_event({
            "type": "status", "inbox": "system",
            "message": "Warm-up engine started",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        })

    def _on_stop(self) -> None:
        self.scheduler.stop()
        self._update_running_state(False)
        self._push_feed_event({
            "type": "status", "inbox": "system",
            "message": "Warm-up engine stopped",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        })

    def _update_running_state(self, running: bool) -> None:
        if running:
            self._status_badge.configure(text="● Running", text_color=SUCCESS)
            self._system_status_lbl.configure(text="Running", text_color=SUCCESS)
            self._start_btn.configure(state="disabled")
            self._stop_btn.configure(state="normal")
        else:
            self._status_badge.configure(text="● Stopped", text_color=WARNING)
            self._system_status_lbl.configure(text="Stopped", text_color=WARNING)
            self._start_btn.configure(state="normal")
            self._stop_btn.configure(state="disabled")

    def _on_reset_counters(self) -> None:
        if not self._confirm("Reset Counters",
                             "Reset all daily sent counters to zero?"):
            return
        self.inbox_store.reset_daily_counts()
        self._refresh_inbox_table()
        self._refresh_stats()
        self._push_feed_event({
            "type": "status", "inbox": "system",
            "message": "Daily counters reset",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        })

    def _on_pause_inbox(self) -> None:
        if not self._selected_inbox:
            self._show_info("Select an inbox row first.")
            return
        inbox = self.inbox_store.find(self._selected_inbox)
        if not inbox:
            return
        if inbox.status == "paused":
            self.inbox_store.resume(inbox.email)
            self._push_feed_event({
                "type": "resume", "inbox": inbox.email,
                "message": "Manually resumed",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            })
        else:
            self.inbox_store.pause(inbox.email, "Manually paused")
            self._push_feed_event({
                "type": "pause", "inbox": inbox.email,
                "message": "Manually paused",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            })
        self._update_inbox_row(inbox.email)

    def _on_delete_inbox(self) -> None:
        if not self._selected_inbox:
            self._show_info("Select an inbox row first.")
            return
        if not self._confirm("Delete Inbox",
                             f"Delete '{self._selected_inbox}'? This cannot be undone."):
            return
        self.inbox_store.delete(self._selected_inbox)
        self._selected_inbox = None
        self._refresh_inbox_table()

    def _on_edit_stage(self) -> None:
        if not self._selected_inbox:
            self._show_info("Select an inbox row first.")
            return
        inbox = self.inbox_store.find(self._selected_inbox)
        if inbox:
            EditStageDialog(self, inbox, self.inbox_store,
                            callback=self._refresh_inbox_table)

    def _on_add_inbox(self) -> None:
        AddInboxDialog(self, self.inbox_store, callback=self._refresh_inbox_table)

    def _on_add_recipients_dialog(self) -> None:
        AddRecipientsDialog(self, self.recipient_store)

    # ================================================================== #
    #  Status Bar                                                          #
    # ================================================================== #

    def _set_statusbar(self, message: str, timeout_ms: int = 8000) -> None:
        self._statusbar_msg.configure(text=message)
        self.after(timeout_ms, lambda: self._statusbar_msg.configure(text=""))

    # ================================================================== #
    #  Helper Dialogs                                                      #
    # ================================================================== #

    def _confirm(self, title: str, message: str) -> bool:
        import tkinter.messagebox as mb
        return mb.askyesno(title, message, parent=self)

    def _show_info(self, message: str) -> None:
        import tkinter.messagebox as mb
        mb.showinfo("Phoenix Warm-Up", message, parent=self)

    def _on_close(self) -> None:
        self.scheduler.shutdown(wait=False)
        self.destroy()


# ================================================================== #
#  Add Inbox Dialog                                                    #
# ================================================================== #

class AddInboxDialog(ctk.CTkToplevel):
    """Modal dialog to add a new Zoho inbox."""

    def __init__(self, parent, inbox_store: InboxStore, callback=None) -> None:
        super().__init__(parent)
        self.inbox_store = inbox_store
        self.callback = callback

        self.title("Add New Inbox")
        self.geometry("500x600")
        self.resizable(False, False)
        self.grab_set()
        self.configure(fg_color=BG)

        # Pre-declare instance vars so _save()/_test_connection() never fail
        # with AttributeError even if somehow called before _build() runs.
        self._entries: Dict[str, ctk.CTkEntry] = {}
        self._stage_var = ctk.StringVar(value="1")
        self._status_lbl: Optional[ctk.CTkLabel] = None

        # Defer widget creation — CTkToplevel needs one event-loop tick to
        # fully initialize its window handle before widgets can be placed.
        self.after(10, self._build)

    def _build(self) -> None:
        # Column 1 (entry fields) must expand to fill available width.
        self.grid_columnconfigure(1, weight=1)
        pad = {"padx": 20, "pady": 6}

        ctk.CTkLabel(
            self, text="Add Zoho Inbox",
            font=ctk.CTkFont(size=18, weight="bold"), text_color=PRIMARY,
        ).grid(row=0, column=0, columnspan=2, **pad, pady=(16, 6))

        fields = [
            ("Email Address", "email", "user@yourdomain.com", False),
            ("App Password", "password", "Zoho app password", True),
            ("Display Name", "display_name", "John Smith", False),
            ("SMTP Host", "smtp_host", "smtp.zoho.in", False),
            ("SMTP Port", "smtp_port", "587", False),
            ("IMAP Host", "imap_host", "imap.zoho.in", False),
            ("IMAP Port", "imap_port", "993", False),
            ("Work Start (HH:MM)", "work_start", "08:00", False),
            ("Work End (HH:MM)", "work_end", "20:00", False),
        ]

        self._entries = {}
        for i, (label, key, placeholder, secret) in enumerate(fields):
            ctk.CTkLabel(
                self, text=label, text_color=MUTED,
                font=ctk.CTkFont(size=11),
            ).grid(row=i + 1, column=0, **pad, sticky="e")

            entry = ctk.CTkEntry(
                self, placeholder_text=placeholder, width=260,
                show="*" if secret else "",
            )
            entry.grid(row=i + 1, column=1, **pad, sticky="w")

            # Pre-fill defaults
            if key in ("smtp_host",):
                entry.insert(0, "smtp.zoho.in")
            elif key in ("imap_host",):
                entry.insert(0, "imap.zoho.in")
            elif key == "smtp_port":
                entry.insert(0, "587")
            elif key == "imap_port":
                entry.insert(0, "993")
            elif key == "work_start":
                entry.insert(0, "08:00")
            elif key == "work_end":
                entry.insert(0, "20:00")

            self._entries[key] = entry

        # Stage selector
        ctk.CTkLabel(self, text="Warm-Up Stage", text_color=MUTED,
                     font=ctk.CTkFont(size=11)).grid(
            row=len(fields) + 1, column=0, **pad, sticky="e"
        )
        self._stage_var = ctk.StringVar(value="1")
        ctk.CTkOptionMenu(
            self, values=["1", "2", "3", "4"],
            variable=self._stage_var, width=80,
        ).grid(row=len(fields) + 1, column=1, **pad, sticky="w")

        # Status message
        self._status_lbl = ctk.CTkLabel(
            self, text="", text_color=WARNING, font=ctk.CTkFont(size=11),
        )
        self._status_lbl.grid(row=len(fields) + 2, column=0, columnspan=2, pady=4)

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=len(fields) + 3, column=0, columnspan=2, pady=12)

        ctk.CTkButton(
            btn_row, text="Test Connection", fg_color=BG_CARD,
            hover_color="#555555", width=140, command=self._test_connection,
        ).grid(row=0, column=0, padx=(0, 10))

        ctk.CTkButton(
            btn_row, text="Save Inbox",
            fg_color=PRIMARY, hover_color="#CC5500",
            width=120, command=self._save,
        ).grid(row=0, column=1)

    def _test_connection(self) -> None:
        email = self._entries["email"].get().strip()
        password = self._entries["password"].get().strip()
        smtp_host = self._entries["smtp_host"].get().strip()
        smtp_port = self._entries["smtp_port"].get().strip()

        if not email or not password:
            self._status_lbl.configure(text="Enter email and password first",
                                       text_color=WARNING)
            return

        self._status_lbl.configure(text="Testing connection...", text_color=MUTED)
        self.update()

        from core.smtp_engine import SMTPEngine
        engine = SMTPEngine(
            host=smtp_host, port=int(smtp_port or 587),
            email=email, password=password,
        )
        ok, msg = engine.test_connection()
        color = SUCCESS if ok else ERROR_COLOR
        self._status_lbl.configure(text=msg, text_color=color)

    def _save(self) -> None:
        email = self._entries["email"].get().strip()
        password = self._entries["password"].get().strip()

        if not email or not password:
            self._status_lbl.configure(text="Email and password are required",
                                       text_color=ERROR_COLOR)
            return

        stage = int(self._stage_var.get())
        try:
            inbox = InboxRecord(
                email=email,
                smtp_host=self._entries["smtp_host"].get().strip() or "smtp.zoho.in",
                smtp_port=int(self._entries["smtp_port"].get().strip() or "587"),
                imap_host=self._entries["imap_host"].get().strip() or "imap.zoho.in",
                imap_port=int(self._entries["imap_port"].get().strip() or "993"),
                password=password,
                stage=stage,
                daily_sent=0,
                daily_limit=get_daily_limit(stage),
                status="active",
                last_sent_at="",
                paused_reason="",
                working_hours_start=self._entries["work_start"].get().strip() or "08:00",
                working_hours_end=self._entries["work_end"].get().strip() or "20:00",
            )
            self.inbox_store.add(inbox)
            if self.callback:
                self.callback()
            self.destroy()
        except ValueError as exc:
            self._status_lbl.configure(text=str(exc), text_color=ERROR_COLOR)
        except Exception as exc:
            self._status_lbl.configure(text=f"Error: {exc}", text_color=ERROR_COLOR)


# ================================================================== #
#  Edit Stage Dialog                                                   #
# ================================================================== #

class EditStageDialog(ctk.CTkToplevel):
    """Simple dialog to change an inbox's warm-up stage."""

    def __init__(self, parent, inbox: InboxRecord, inbox_store: InboxStore,
                 callback=None) -> None:
        super().__init__(parent)
        self.inbox = inbox
        self.inbox_store = inbox_store
        self.callback = callback

        self.title("Edit Warm-Up Stage")
        self.geometry("340x200")
        self.resizable(False, False)
        self.grab_set()
        self.configure(fg_color=BG)

        # Pre-declare before deferred build so _save() is always safe
        self._var = ctk.StringVar(value=str(inbox.stage))
        self.after(10, self._build)

    def _build(self) -> None:
        ctk.CTkLabel(
            self, text=f"Inbox: {self.inbox.email}",
            font=ctk.CTkFont(size=12), text_color=MUTED,
        ).pack(pady=(16, 4), padx=20)

        ctk.CTkLabel(self, text="Select Stage:", text_color=ACCENT).pack(pady=4)
        ctk.CTkOptionMenu(
            self, values=["1", "2", "3", "4"], variable=self._var,
        ).pack(pady=8)

        ctk.CTkButton(
            self, text="Update Stage", fg_color=PRIMARY,
            hover_color="#CC5500", command=self._save,
        ).pack(pady=12)

    def _save(self) -> None:
        new_stage = int(self._var.get())
        self.inbox_store.update_stage(self.inbox.email, new_stage)
        if self.callback:
            self.callback()
        self.destroy()


# ================================================================== #
#  Add Recipients Dialog                                               #
# ================================================================== #

class AddRecipientsDialog(ctk.CTkToplevel):
    """Dialog to add recipient emails or seed with Faker."""

    def __init__(self, parent, recipient_store: RecipientStore) -> None:
        super().__init__(parent)
        self.recipient_store = recipient_store

        self.title("Manage Recipients")
        self.geometry("460x380")
        self.resizable(False, False)
        self.grab_set()
        self.configure(fg_color=BG)

        # Pre-declare so _add_manual()/_seed_faker() are always safe
        self._email_entry: Optional[ctk.CTkEntry] = None
        self._seed_count: Optional[ctk.CTkEntry] = None
        self._count_lbl: Optional[ctk.CTkLabel] = None
        self._status_lbl: Optional[ctk.CTkLabel] = None

        self.after(10, self._build)

    def _build(self) -> None:
        ctk.CTkLabel(
            self, text="Recipients Pool",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=PRIMARY,
        ).pack(pady=(16, 4))

        count = len(self.recipient_store.get_active())
        self._count_lbl = ctk.CTkLabel(
            self, text=f"Active recipients: {count}", text_color=MUTED,
        )
        self._count_lbl.pack(pady=4)

        # Manual add
        ctk.CTkLabel(self, text="Add email manually:", text_color=ACCENT).pack(pady=(12, 2))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=4)
        self._email_entry = ctk.CTkEntry(row, placeholder_text="email@example.com",
                                          width=260)
        self._email_entry.grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(row, text="Add", width=70, fg_color=PRIMARY,
                      command=self._add_manual).grid(row=0, column=1)

        ctk.CTkLabel(
            self, text="— or —", text_color=MUTED, font=ctk.CTkFont(size=11),
        ).pack(pady=8)

        # Faker seed
        ctk.CTkLabel(self, text="Auto-generate test recipients:",
                     text_color=ACCENT).pack(pady=(0, 4))
        seed_row = ctk.CTkFrame(self, fg_color="transparent")
        seed_row.pack(pady=4)
        self._seed_count = ctk.CTkEntry(seed_row, placeholder_text="100",
                                         width=80)
        self._seed_count.insert(0, "100")
        self._seed_count.grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(seed_row, text="Generate with Faker", width=160,
                      fg_color="#1565C0", hover_color="#0D47A1",
                      command=self._seed_faker).grid(row=0, column=1)

        self._status_lbl = ctk.CTkLabel(self, text="", text_color=MUTED,
                                         font=ctk.CTkFont(size=11))
        self._status_lbl.pack(pady=8)

    def _add_manual(self) -> None:
        email = self._email_entry.get().strip()
        if not email or "@" not in email:
            self._status_lbl.configure(text="Enter a valid email address",
                                        text_color=ERROR_COLOR)
            return
        from storage.recipient_store import RecipientRecord
        rec = RecipientRecord(email=email, name=email.split("@")[0])
        self.recipient_store.add(rec)
        self._email_entry.delete(0, "end")
        self._refresh_count()
        self._status_lbl.configure(text=f"Added {email}", text_color=SUCCESS)

    def _seed_faker(self) -> None:
        try:
            count = int(self._seed_count.get().strip() or "100")
        except ValueError:
            count = 100
        self._status_lbl.configure(text=f"Generating {count} recipients...",
                                    text_color=MUTED)
        self.update()
        self.recipient_store.seed_with_faker(count)
        self._refresh_count()
        self._status_lbl.configure(
            text=f"Done! Generated recipients added.", text_color=SUCCESS,
        )

    def _refresh_count(self) -> None:
        count = len(self.recipient_store.get_active())
        self._count_lbl.configure(text=f"Active recipients: {count}")
