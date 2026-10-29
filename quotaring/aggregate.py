"""Group recorded usage events into the periods shown by the widget."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from .model import PeriodUsage, Tokens, UsageEvent

PERIODS = (
    ("today", "Today"),
    ("5h", "Last 5 hours"),
    ("7d", "Last 7 days"),
    ("30d", "Last 30 days"),
    ("all", "All scanned"),
)
RETENTION_DAYS = 35


def period_starts(now: float) -> dict[str, float | None]:
    local_now = datetime.fromtimestamp(now).astimezone()
    midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        "today": midnight.timestamp(),
        "5h": now - 5 * 3600,
        "7d": now - 7 * 86400,
        "30d": now - 30 * 86400,
        "all": None,
    }


def retention_cutoff(now: float) -> float:
    return (datetime.fromtimestamp(now) - timedelta(days=RETENTION_DAYS)).timestamp()


def aggregate(events: Iterable[UsageEvent], now: float) -> list[PeriodUsage]:
    starts = period_starts(now)
    out = {k: PeriodUsage(key=k, label=label) for k, label in PERIODS}
    for ev in events:
        for key, start in starts.items():
            if start is not None and (ev.ts is None or ev.ts < start or ev.ts > now + 300):
                continue
            p = out[key]
            p.total.add(ev.tokens)
            p.by_model.setdefault(ev.model, Tokens()).add(ev.tokens)
            p.events += 1
    return [out[k] for k, _ in PERIODS]


def daily_totals(events: Iterable[UsageEvent], now: float, days: int = 14) -> list[list]:
    """[[local date 'YYYY-MM-DD', total tokens], ...] for the last `days` days, oldest first."""
    today = datetime.fromtimestamp(now).date()
    keys = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    totals = dict.fromkeys(keys, 0)
    for ev in events:
        if ev.ts is None or ev.ts > now + 300:
            continue
        day = datetime.fromtimestamp(ev.ts).date().isoformat()
        if day in totals:
            totals[day] += ev.tokens.total
    return [[k, totals[k]] for k in keys]
