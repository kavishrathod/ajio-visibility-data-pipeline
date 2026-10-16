"""Time helpers: slots are UTC hours; IST is only a display convenience."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ist_label(value: str | datetime) -> str:
    """'2026-10-16T05:00:00Z' -> '2026-10-16 10:30 IST'."""
    dt = value if isinstance(value, datetime) else parse_utc(value)
    return dt.astimezone(IST).strftime("%Y-%m-%d %H:%M IST")


def utc_label(value: str | datetime) -> str:
    dt = value if isinstance(value, datetime) else parse_utc(value)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def slot_label(value: str) -> str:
    """Human label with both zones, e.g. '2026-10-16 05:00 UTC (2026-10-16 10:30 IST)'."""
    return f"{utc_label(value)} ({ist_label(value)})"
