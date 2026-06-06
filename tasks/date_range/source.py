"""Date-range helpers built on the standard library date type."""

from datetime import date, timedelta


def days_between(start: date, end: date) -> int:
    """Inclusive-exclusive day count; negative if end precedes start."""
    return (end - start).days


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def business_days(start: date, end: date) -> int:
    if end < start:
        raise ValueError("end must not precede start")
    count = 0
    cur = start
    while cur < end:
        if not is_weekend(cur):
            count += 1
        cur += timedelta(days=1)
    return count


def add_business_days(start: date, n: int) -> date:
    if n < 0:
        raise ValueError("n must be non-negative")
    cur = start
    added = 0
    while added < n:
        cur += timedelta(days=1)
        if not is_weekend(cur):
            added += 1
    return cur
