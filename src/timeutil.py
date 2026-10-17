"""Time helpers.

A *slot* (scheduled_hour) is the top of an hour in IST (Asia/Kolkata, UTC+05:30).
It is stored as a UTC instant, so 10:00 IST is stored as 2026-10-16T04:30:00Z.
Storing UTC keeps comparisons and sorting unambiguous; flooring in IST makes the
slot match the hour a person in Mumbai means by "the 10:00 run".
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def floor_to_slot(dt: datetime) -> datetime:
    """Floor an instant to the top of its IST hour; return it as an aware UTC datetime."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(IST).replace(minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc)


def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ist_label(value: str | datetime) -> str:
    """'2026-10-16T04:30:00Z' -> '2026-10-16 10:00 IST'."""
    dt = value if isinstance(value, datetime) else parse_utc(value)
    return dt.astimezone(IST).strftime("%Y-%m-%d %H:%M IST")


def utc_label(value: str | datetime) -> str:
    dt = value if isinstance(value, datetime) else parse_utc(value)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def slot_label(value: str) -> str:
    """Human label with both zones, e.g. '2026-10-16 04:30 UTC (2026-10-16 10:00 IST)'."""
    return f"{utc_label(value)} ({ist_label(value)})"
