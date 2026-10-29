"""Quota notifications shared by the tray app and the Plasma widget.

Which alerts were already shown is kept in one small file, so a notification appears once per
limit window even when both front ends run, or after a restart.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import paths
from .i18n import tr, tr_label
from .jsonstore import read_json, write_json
from .model import State
from .ui import format as fmt


def pending(snapshots, threshold: int, now: float) -> list[dict]:
    """Alerts the current snapshots warrant: limit reached, or a fresh reading at/over threshold."""
    out = []
    if not threshold:
        return out
    for snap in snapshots:
        for w in snap.quota.windows:
            if w.resets_at is not None and w.resets_at <= now:
                continue  # already reset: the reading no longer applies
            if w.active_limit(now):
                key, title, body = f"{snap.provider_id}|{w.key}|{w.resets_at}|limit", \
                    tr("{name}: {label} limit reached"), fmt.resets(w.resets_at, now)
            elif snap.quota.state == State.OK and w.used_percent >= threshold:
                # only verified, fresh percentages trigger threshold notifications
                key, title, body = f"{snap.provider_id}|{w.key}|{w.resets_at}", \
                    tr("{name}: {label} at {pct}%"), tr("Reported by the provider's account interface.")
            else:
                continue
            out.append({"key": key, "expires": w.resets_at or now + 7 * 86400, "body": body,
                        "title": title.format(name=snap.name, label=tr_label(w.label),
                                              pct=f"{w.used_percent:.0f}")})
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
