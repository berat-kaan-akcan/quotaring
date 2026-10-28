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


def summary(snapshots, now: float) -> str:
    """One line per provider for the tray tooltip. Quota only when provider-reported."""
    lines = []
    for s in snapshots:
        q, loc = s.quota, s.local
        parts = []
        if q.state in (State.OK, State.STALE) and q.windows:
            parts.append(" · ".join(f"{w.label.split(' ')[0]} {w.used_percent:.0f}%" for w in q.windows[:2]))
            if q.state == State.STALE:
                parts[-1] += " (stale)"
        per = loc.period("today") if loc.state in (State.OK, State.STALE) else None
        if per is not None:
            parts.append(f"today {tokens(per.total.total)} tok")
        if not parts:
            parts.append(STATE_TEXT[loc.state if loc.state != State.OK else q.state])
        lines.append(f"{s.name}: " + ", ".join(parts))
    return "\n".join(lines)
