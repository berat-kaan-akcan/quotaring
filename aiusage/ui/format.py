"""Text formatting for the UI (pure functions, unit tested)."""

from __future__ import annotations

from datetime import datetime

from ..model import State

STATE_TEXT = {
    State.OK: "OK",
    State.STALE: "Stale",
    State.NOT_INSTALLED: "Not installed",
    State.NOT_AUTHENTICATED: "Not authenticated",
    State.RATE_LIMITED: "Rate limited",
    State.UNAVAILABLE: "Unavailable",
    State.UNSUPPORTED: "Unsupported",
    State.DISABLED: "Disabled",
    State.PENDING: "Loading…",
}


def tokens(n: int) -> str:
    n = int(n)
    for div, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n >= div:
            v = n / div
            return f"{v:.1f}{suffix}" if v < 100 else f"{v:.0f}{suffix}"
    return str(n)


def duration(seconds: float) -> str:
    s = int(max(0, seconds))
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m = s // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def resets(resets_at: float | None, now: float) -> str:
    if resets_at is None:
        return "reset time unknown"
    if resets_at <= now:
        return "reset passed · awaiting refresh"
    when = datetime.fromtimestamp(resets_at).astimezone()
    if resets_at - now < 86400:
        return f"resets in {duration(resets_at - now)}"
    return f"resets {when.strftime('%a %H:%M')} ({duration(resets_at - now)})"


def age(ts: float | None, now: float) -> str:
    if ts is None:
        return "never"
    delta = now - ts
    if delta < 60:
        return "just now"
    return f"{duration(delta)} ago"


def updated(ts: float | None, now: float) -> str:
    if ts is None:
        return "not updated yet"
    return f"updated {datetime.fromtimestamp(ts).strftime('%H:%M')} ({age(ts, now)})"
