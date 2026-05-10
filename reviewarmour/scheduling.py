"""Scheduling helpers for sequence timing (Sunday deferral)."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

EST = ZoneInfo("America/New_York")


def defer_sunday_touch_to_monday_8am_est(dt: datetime) -> datetime:
    """
    If `dt` falls on Sunday in America/New_York, move to the following Monday 08:00 EST.
    Otherwise return dt unchanged. Naive datetimes are treated as America/New_York.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=EST)
    local = dt.astimezone(EST)
    if local.weekday() != 6:
        return dt
    nxt = local.date() + timedelta(days=1)
    return datetime.combine(nxt, time(8, 0, tzinfo=EST))
