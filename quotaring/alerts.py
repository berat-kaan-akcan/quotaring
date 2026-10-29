"""Quota notifications.

Which alerts were already shown is kept in one small file, so a notification appears once per
limit window, also after a restart.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from . import paths
from .i18n import tr, tr_label
from .jsonstore import read_json, write_json
from .model import State
from .ui import format as fmt


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


def pending(snapshots, threshold: int, now: float) -> list[dict]:
    """Alerts the current snapshots warrant: limit reached, or a fresh reading at/over threshold."""
    out = []
    if not threshold:
        return out
    for snap in snapshots:
        for w in snap.quota.windows:
            if w.resets_at is not None and w.resets_at <= now:
                continue  # already reset: the reading no longer applies
            resets = fmt.resets(w.resets_at, now)
            limit = limit_name(w.label)
            if w.active_limit(now):
                key = f"{snap.provider_id}|{w.key}|{w.resets_at}|limit"
                title = tr("{name} · {limit} reached").format(name=snap.name, limit=limit)
                body = _sentence(resets)
            elif snap.quota.state == State.OK and w.used_percent >= threshold:
                # only verified, fresh percentages trigger threshold notifications
                key = f"{snap.provider_id}|{w.key}|{w.resets_at}"
                title = tr("{name} · {limit}: {pct} left").format(
                    name=snap.name, limit=limit, pct=fmt.pct(max(0.0, 100 - w.used_percent)))
                body = tr("{pct} used · {resets}").format(pct=fmt.pct(w.used_percent), resets=resets)
            else:
                continue
            out.append({"key": key, "expires": w.resets_at or now + 7 * 86400, "title": title, "body": body})
    return out


class Seen:
    """Persistent set of alert keys already shown; entries expire with their window."""

    def __init__(self, path: Path | None = None):
        self.path = path or paths.cache_dir() / "notified-v1.json"

    def take_new(self, alerts: list[dict], now: float | None = None) -> list[dict]:
        now = now or time.time()
        data = read_json(self.path, {})
        seen = {k: v for k, v in data.items() if isinstance(v, (int, float)) and v > now} \
            if isinstance(data, dict) else {}
        new = [a for a in alerts if a["key"] not in seen]
        for a in new:
            seen[a["key"]] = a["expires"]
        if new or len(seen) != len(data if isinstance(data, dict) else {}):
            try:
                write_json(self.path, seen)
            except OSError:
                pass
        return new
