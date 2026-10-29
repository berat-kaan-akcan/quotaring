"""Quota notifications.

Which alerts were already shown is kept in one small file, so a notification appears once per
limit window, also after a restart.

Keys never contain the reset time itself: providers report it with a little jitter on every poll
(a fraction of a second, sometimes more), which would make each poll look like a new window.
A key is "provider|limit|kind" and remembers until when its window runs; a later window can alert
again once that moment (plus a grace period) has passed.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterable
from pathlib import Path

from . import paths
from .i18n import tr, tr_label
from .jsonstore import read_json, write_json
from .model import State
from .ui import format as fmt

LEVELS = (50, 75, 80, 90, 95)  # warning levels offered in the settings (percent used)
GRACE = 60  # seconds a key outlives its window: absorbs jitter (seen: under a second) in the reported reset time
RESET_FRESH = 30 * 60  # a "limit reset" alert only for resets that happened this recently


def limit_name(label: str) -> str:
    """'Weekly' -> 'Weekly limit', '5-hour session · Gemini' -> '5-hour limit (Gemini)'."""
    kind, _, scope = label.partition(" · ")
    m = re.fullmatch(r"(\d+)-(hour session|minute|day)", kind)
    if m:
        kind = tr({"hour session": "{n}-hour", "minute": "{n}-minute", "day": "{n}-day"}[m.group(2)]).format(n=m.group(1))
    else:
        kind = tr_label(kind)
    name = tr("{kind} limit").format(kind=kind)
    return f"{name} ({scope})" if scope else name


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:] + "."


def _levels(levels: int | Iterable[int] | None) -> list[int]:
    if not levels:
        return []
    if isinstance(levels, (int, float)):
        levels = [levels]
    return sorted({int(n) for n in levels if 0 < int(n) <= 100})


def pending(snapshots, levels: int | Iterable[int] | None, now: float, *, limit_reached: bool = True,
            reset: bool = False) -> list[dict]:
    """Alerts the current snapshots warrant.

    `levels`: percentages used that warn (only fresh, provider-reported readings); the highest one
    crossed is shown and the lower ones count as shown with it. `limit_reached`: a limit hit.
    `reset`: a limit that was full has just reset.
    """
    out = []
    levels = _levels(levels)
    for snap in snapshots:
        for w in snap.quota.windows:
            base = f"{snap.provider_id}|{w.key}"
            limit = limit_name(w.label)
            if w.resets_at is not None and w.resets_at <= now:
                # already reset: the reading no longer applies, apart from saying so
                if reset and (w.limited or w.used_percent >= 99.5) and now - w.resets_at <= RESET_FRESH:
                    out.append({"key": f"{base}|reset", "also": [], "expires": now + RESET_FRESH + GRACE,
                                "title": tr("{name} · {limit} reset").format(name=snap.name, limit=limit),
                                "body": tr("The full quota is available again."), "used": 0.0, "limited": False})
                continue
            expires = (w.resets_at or now + 7 * 86400) + GRACE
            resets = fmt.resets(w.resets_at, now)
            if w.active_limit(now):
                if not limit_reached:
                    continue
                title = tr("{name} · {limit} reached").format(name=snap.name, limit=limit)
                out.append({"key": f"{base}|limit", "also": [f"{base}|{n}" for n in levels], "expires": expires,
                            "title": title, "body": _sentence(resets), "used": 100.0, "limited": True})
                continue
            if snap.quota.state != State.OK:
                continue  # only verified, fresh percentages trigger level notifications
            crossed = [n for n in levels if w.used_percent >= n]
            if not crossed:
                continue
            title = tr("{name} · {limit}: {pct} left").format(
                name=snap.name, limit=limit, pct=fmt.pct(max(0.0, 100 - w.used_percent)))
            body = tr("{pct} used · {resets}").format(pct=fmt.pct(w.used_percent), resets=resets)
            out.append({"key": f"{base}|{crossed[-1]}", "also": [f"{base}|{n}" for n in crossed[:-1]],
                        "expires": expires, "title": title, "body": body, "used": w.used_percent, "limited": False})
    return out


class Seen:
    """Persistent set of alert keys already shown; entries expire with their window."""

    def __init__(self, path: Path | None = None):
        self.path = path or paths.cache_dir() / "notified-v2.json"

    def take_new(self, alerts: list[dict], now: float | None = None) -> list[dict]:
        """The alerts not shown yet, now recorded as shown (with the lower levels they cover)."""
        now = now or time.time()
        data = read_json(self.path, None)
        data = data if isinstance(data, dict) else self._from_v1()
        seen = {k: v for k, v in data.items() if isinstance(v, (int, float)) and v > now}
        new = [a for a in alerts if a["key"] not in seen]
        for a in new:
            for k in [a["key"], *a.get("also", ())]:
                seen[k] = max(seen.get(k, 0), a["expires"])
        if new or seen != data:
            try:
                write_json(self.path, seen)
            except OSError:
                pass
        return new

    def _from_v1(self) -> dict:
        """Keys of the old file ("provider|limit|reset time[|limit]"), so an upgrade does not repeat them."""
        old = read_json(self.path.with_name("notified-v1.json"), {})
        out: dict = {}
        for k, v in (old.items() if isinstance(old, dict) else ()):
            parts = k.split("|")
            if not isinstance(v, (int, float)) or len(parts) < 3:
                continue
            base = "|".join(parts[:2])
            for key in [f"{base}|limit"] if parts[-1] == "limit" else [f"{base}|{n}" for n in LEVELS]:
                out[key] = max(out.get(key, 0), v + GRACE)
        return out
