"""Text formatting for the UI (pure functions, unit tested)."""

from __future__ import annotations

from datetime import datetime

from ..i18n import language, tr, tr_label, weekday

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
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


def state_text(state: State) -> str:
    return tr(STATE_TEXT[state])


def pct(value: float) -> str:
    """'24%' in English, '%24' in Turkish."""
    return f"%{value:.0f}" if language() == "tr" else f"{value:.0f}%"


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
    ud, uh, um = ("g", "sa", "dk") if language() == "tr" else ("d", "h", "m")
    if d:
        return f"{d}{ud} {h}{uh}"
    if h:
        return f"{h}{uh} {m}{um}"
    return f"{m}{um}"


def resets(resets_at: float | None, now: float) -> str:
    if resets_at is None:
        return tr("reset time unknown")
    if resets_at <= now:
        return tr("reset passed · awaiting refresh")
    when = datetime.fromtimestamp(resets_at).astimezone()
    if resets_at - now < 86400:
        return tr("resets in {d}").format(d=duration(resets_at - now))
    # Not strftime('%a'): Qt sets the process locale, which would leak e.g. Turkish into English.
    stamp = f"{weekday(WEEKDAYS[when.weekday()])} {when.strftime('%H:%M')}"
    return tr("resets {when} ({d})").format(when=stamp, d=duration(resets_at - now))


def age(ts: float | None, now: float) -> str:
    if ts is None:
        return tr("never")
    delta = now - ts
    if delta < 60:
        return tr("just now")
    return tr("{d} ago").format(d=duration(delta))


def updated(ts: float | None, now: float) -> str:
    if ts is None:
        return tr("not updated yet")
    return tr("updated {time} ({age})").format(time=datetime.fromtimestamp(ts).strftime('%H:%M'), age=age(ts, now))


def window_pct(w, now: float) -> str:
    """Percentage text for a quota window, or "Limit reached" while the provider rejects requests."""
    return tr("Limit reached") if w.active_limit(now) else pct(w.used_percent)


def summary(snapshots, now: float) -> str:
    """One line per provider for the tray tooltip. Quota only when provider-reported."""
    lines = []
    for s in snapshots:
        q, loc = s.quota, s.local
        parts = []
        if q.state in (State.OK, State.STALE) and q.windows:
            if language() == "tr":
                names = [tr_label(w.label).split(" · ")[0] for w in q.windows[:2]]
            else:
                names = [w.label.split(" ")[0] for w in q.windows[:2]]
            parts.append(" · ".join(f"{n} {window_pct(w, now)}" for n, w in zip(names, q.windows[:2])))
            if q.state == State.STALE:
                parts[-1] += tr(" (stale)")
        per = loc.period("today") if loc.state in (State.OK, State.STALE) else None
        if per is not None:
            parts.append(tr("today {v} tok").format(v=tokens(per.total.total)))
        if not parts:
            parts.append(state_text(loc.state if loc.state != State.OK else q.state))
        lines.append(f"{s.name}: " + ", ".join(parts))
    return "\n".join(lines)
