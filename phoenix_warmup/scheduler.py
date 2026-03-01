"""
scheduler.py
APScheduler BackgroundScheduler setup for Phoenix Warm-Up Engine.
All jobs run in background threads — never blocks the UI.

Jobs:
  warmup_cycle  — every 60 seconds: WarmupEngine.run_cycle()
  reply_cycle   — every 5 minutes : ReplyEngine.run_reply_cycle()
  imap_scan     — every 15 minutes: ReplyEngine.run_reply_cycle() (alias)
  daily_reset   — cron 00:00      : InboxStore.reset_daily_counts()
"""
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import STATE_PAUSED
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

logger = logging.getLogger("phoenix.scheduler")


class WarmupScheduler:
    """
    Wraps APScheduler BackgroundScheduler.
    start() / stop() are called by the UI Start/Stop buttons.
    """

    JOB_WARMUP = "warmup_cycle"
    JOB_REPLY = "reply_cycle"
    JOB_RESET = "daily_reset"

    def __init__(
        self,
        warmup_engine,
        reply_engine,
        inbox_store,
        ui_queue,
    ) -> None:
        self._warmup_engine = warmup_engine
        self._reply_engine = reply_engine
        self._inbox_store = inbox_store
        self._ui_queue = ui_queue
        self._running = False

        executors = {
            "default": ThreadPoolExecutor(max_workers=4),
        }
        job_defaults = {
            "coalesce": True,          # Merge missed runs into one
            "max_instances": 1,        # Never run the same job twice at once
            "misfire_grace_time": 120, # Allow up to 2 min late start
        }

        self._scheduler = BackgroundScheduler(
            executors=executors,
            job_defaults=job_defaults,
        )
        self._scheduler.add_listener(
            self._on_job_event,
            EVENT_JOB_ERROR | EVENT_JOB_EXECUTED,
        )

    # ------------------------------------------------------------------ #
    # Lifecycle                                                             #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Register all jobs and start the background scheduler."""
        if self._running:
            return

        # Warm-up send cycle: every 60 seconds
        self._scheduler.add_job(
            func=self._warmup_engine.run_cycle,
            trigger=IntervalTrigger(seconds=60),
            id=self.JOB_WARMUP,
            name="Warm-Up Send Cycle",
            replace_existing=True,
        )

        # Reply / IMAP scan cycle: every 5 minutes
        self._scheduler.add_job(
            func=self._reply_engine.run_reply_cycle,
            trigger=IntervalTrigger(minutes=5),
            id=self.JOB_REPLY,
            name="IMAP Scan & Reply Cycle",
            replace_existing=True,
        )

        # Daily counter reset: every day at 00:00:30
        self._scheduler.add_job(
            func=self._inbox_store.reset_daily_counts,
            trigger=CronTrigger(hour=0, minute=0, second=30),
            id=self.JOB_RESET,
            name="Daily Counter Reset",
            replace_existing=True,
        )

        # If scheduler was previously paused (Stop → Start), resume it.
        # Calling start() on a paused scheduler raises SchedulerAlreadyRunningError.
        if self._scheduler.state == STATE_PAUSED:
            self._scheduler.resume()
        else:
            self._scheduler.start()
        self._running = True
        logger.info("WarmupScheduler started")
        self._post_ui("status", "system", "Scheduler started")

    def stop(self) -> None:
        """Pause all jobs (doesn't destroy the scheduler)."""
        if not self._running:
            return
        self._scheduler.pause()
        self._running = False
        logger.info("WarmupScheduler paused")
        self._post_ui("status", "system", "Scheduler stopped")

    def resume(self) -> None:
        """Resume after stop()."""
        if self._running:
            return
        self._scheduler.resume()
        self._running = True
        logger.info("WarmupScheduler resumed")
        self._post_ui("status", "system", "Scheduler resumed")

    def shutdown(self, wait: bool = False) -> None:
        """Full shutdown — called on application exit."""
        try:
            self._scheduler.shutdown(wait=wait)
        except Exception:
            pass
        self._running = False

    # ------------------------------------------------------------------ #
    # Status helpers                                                        #
    # ------------------------------------------------------------------ #

    def is_running(self) -> bool:
        return self._running

    def get_next_run(self, job_id: str) -> str:
        """Return ISO datetime string of next run for a job, or ''."""
        try:
            job = self._scheduler.get_job(job_id)
            if job and job.next_run_time:
                return job.next_run_time.strftime("%H:%M:%S")
        except Exception:
            pass
        return ""

    # ------------------------------------------------------------------ #
    # Job event listener                                                    #
    # ------------------------------------------------------------------ #

    def _on_job_event(self, event) -> None:
        if hasattr(event, "exception") and event.exception:
            logger.error(
                f"Job {event.job_id} failed: {event.exception}",
                exc_info=(
                    type(event.exception),
                    event.exception,
                    event.exception.__traceback__,
                ),
            )
            self._post_ui("error", "system",
                          f"Job {event.job_id} error: {event.exception}")

    def _post_ui(self, event_type: str, inbox: str, message: str) -> None:
        """Non-blocking post to UI queue."""
        try:
            self._ui_queue.put_nowait({
                "type": event_type,
                "inbox": inbox,
                "message": message,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            })
        except Exception:
            pass
