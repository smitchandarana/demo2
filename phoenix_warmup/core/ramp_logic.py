"""
core/ramp_logic.py
Stage-based ramp logic for email warm-up.
Pure functions: no I/O, no side effects, easily testable.
"""
import os
import random
from datetime import datetime

# Stage → emails per day limit
STAGE_LIMITS = {
    1: 5,
    2: 15,
    3: 25,
    4: 40,
}

MAX_STAGE = 4

# Minimum interval between sends per stage (seconds): (min, max)
STAGE_SEND_INTERVALS = {
    1: (1800, 10800),   # 30 min – 3 hours
    2: (900,  5400),    # 15 min – 90 min
    3: (600,  3600),    # 10 min – 60 min
    4: (300,  2400),    # 5 min  – 40 min
}

# Reply delay range per stage (seconds)
REPLY_DELAY_RANGE = (300, 2700)   # 5 – 45 minutes


def get_daily_limit(stage: int) -> int:
    """Return the daily send limit for a given stage."""
    return STAGE_LIMITS.get(stage, STAGE_LIMITS[1])


def should_send(inbox: dict) -> bool:
    """
    Return True if the inbox has not yet hit its daily limit.
    inbox: dict with keys 'daily_sent' and 'daily_limit'
    """
    sent = int(inbox.get("daily_sent", 0))
    limit = int(inbox.get("daily_limit", get_daily_limit(1)))
    return sent < limit


def get_send_delay_seconds(stage: int) -> int:
    """Return a random delay (seconds) between sends for this stage."""
    low, high = STAGE_SEND_INTERVALS.get(stage, STAGE_SEND_INTERVALS[1])
    base = random.uniform(low, high)
    # Gaussian jitter ±10% of range
    jitter = random.gauss(0, (high - low) * 0.05)
    return max(int(low * 0.5), int(base + jitter))


def get_reply_delay_seconds() -> int:
    """Return a random reply delay (5-45 minutes)."""
    low, high = REPLY_DELAY_RANGE
    return int(random.uniform(low, high))


def within_working_hours(start_str: str = None, end_str: str = None) -> bool:
    """
    Check if current local time is within configured working hours.
    Reads WORK_START / WORK_END from environment if not provided.
    Format: 'HH:MM' (24-hour).
    """
    if start_str is None:
        start_str = os.environ.get("WORK_START", "08:00")
    if end_str is None:
        end_str = os.environ.get("WORK_END", "20:00")

    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute

    def parse(s: str) -> int:
        h, m = map(int, s.split(":"))
        return h * 60 + m

    start = parse(start_str)
    end = parse(end_str)

    if start <= end:
        return start <= current_minutes <= end
    # Overnight window (e.g. 22:00 – 06:00)
    return current_minutes >= start or current_minutes <= end


def check_bounce_threshold(inbox: dict) -> bool:
    """
    Return True if the inbox's bounce rate exceeds the threshold.
    inbox: dict with 'bounced_today' and 'sent_today' keys.
    Threshold from BOUNCE_THRESHOLD env var (default 0.05 = 5%).
    """
    threshold = float(os.environ.get("BOUNCE_THRESHOLD", "0.05"))
    sent = int(inbox.get("daily_sent", 0))
    bounced = int(inbox.get("bounced_today", 0))
    if sent == 0:
        return False
    return (bounced / sent) > threshold


def is_time_to_send(last_sent_at: str, stage: int) -> bool:
    """
    Return True if enough time has passed since last_sent_at to send again.
    last_sent_at: ISO datetime string or empty string.
    """
    if not last_sent_at:
        return True
    try:
        last = datetime.fromisoformat(last_sent_at)
    except ValueError:
        return True
    delay = get_send_delay_seconds(stage)
    elapsed = (datetime.now() - last).total_seconds()
    return elapsed >= delay


def next_stage(current_stage: int) -> int:
    """Return the next stage, capped at MAX_STAGE."""
    return min(current_stage + 1, MAX_STAGE)
