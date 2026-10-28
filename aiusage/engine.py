"""Refresh bookkeeping, last-good-result caching and stale handling (UI independent)."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from . import paths
from .jsonstore import read_json, write_json
from .model import LocalUsage, ProviderSnapshot, Quota, State

log = logging.getLogger(__name__)
CACHE_VERSION = 1
RATE_LIMIT_BACKOFF = 15 * 60


def merge_local(prev: LocalUsage | None, new: LocalUsage) -> LocalUsage:
    """Keep the last good numbers visible, marked stale, when a refresh fails."""
    if new.state == State.OK or prev is None:
        return new
    if prev.state in (State.OK, State.STALE) and prev.periods and new.state == State.UNAVAILABLE:
        return LocalUsage(State.STALE, prev.periods, prev.source, prev.exact,
                          detail=new.detail, files=prev.files, updated_at=prev.updated_at)
    return new


def merge_quota(prev: Quota | None, new: Quota) -> Quota:
    if new.state == State.OK or prev is None:
        return new
    transient = new.state in (State.UNAVAILABLE, State.RATE_LIMITED)
    if prev.state in (State.OK, State.STALE) and prev.windows and transient:
        return Quota(State.STALE, prev.windows, prev.plan, prev.source, prev.documented,
                     detail=new.detail, extra=prev.extra, updated_at=prev.updated_at)
    return new


class Engine:
    def __init__(self, settings, providers, cache_path: Path | None = None):
        self.settings = settings
        self.providers = {p.id: p for p in providers}
        self.cache_path = cache_path or paths.cache_dir() / f"snapshots-v{CACHE_VERSION}.json"
        self.lock = threading.Lock()
        self.busy: set[tuple[str, str]] = set()
        self.next_quota_at: dict[str, float] = {}
        self.snapshots: dict[str, ProviderSnapshot] = {}
        for p in providers:
            self.snapshots[p.id] = ProviderSnapshot(p.id, p.name, LocalUsage(State.PENDING), Quota(State.PENDING))
        self._load_cache()

    # -- cache ----------------------------------------------------------
    def _load_cache(self) -> None:
        data = read_json(self.cache_path, {})
        if not isinstance(data, dict) or data.get("version") != CACHE_VERSION:
            return
        for pid, raw in (data.get("snapshots") or {}).items():
            if pid not in self.snapshots:
                continue
            try:
                snap = ProviderSnapshot.from_dict(raw)
            except (KeyError, ValueError, TypeError):
                continue
            # Cached values are shown as stale until a fresh refresh succeeds.
            if snap.local.state == State.OK:
                snap.local.state = State.STALE
                snap.local.detail = "Cached result; refreshing"
            if snap.quota.state == State.OK:
                snap.quota.state = State.STALE
                snap.quota.detail = "Cached result; refreshing"
            self.snapshots[pid] = snap

    def save_cache(self) -> None:
        with self.lock:
            data = {"version": CACHE_VERSION,
                    "snapshots": {pid: s.to_dict() for pid, s in self.snapshots.items()}}
        try:
            write_json(self.cache_path, data)
        except OSError:
            log.warning("could not write snapshot cache %s", self.cache_path)

    # -- scheduling -----------------------------------------------------
    def enabled(self, pid: str) -> bool:
        return bool(self.settings.providers_enabled.get(pid, True))

    def quota_enabled(self, pid: str) -> bool:
        return self.enabled(pid) and bool(self.settings.quota_enabled.get(pid, True))

    def try_begin(self, pid: str, kind: str) -> bool:
        with self.lock:
            if (pid, kind) in self.busy:
                return False
            self.busy.add((pid, kind))
            return True

    def end(self, pid: str, kind: str) -> None:
        with self.lock:
            self.busy.discard((pid, kind))

    def quota_due(self, pid: str, now: float, force: bool = False) -> bool:
        if force:
            return True
        return now >= self.next_quota_at.get(pid, 0)

    # -- work (runs on worker threads) -----------------------------------
    def run_local(self, pid: str, now: float | None = None) -> LocalUsage:
        now = now or time.time()
        if not self.enabled(pid):
            return LocalUsage(State.DISABLED, detail="Disabled in settings", updated_at=now)
        return self.providers[pid].collect_local(now)

    def run_quota(self, pid: str, now: float | None = None) -> Quota:
        now = now or time.time()
        if not self.quota_enabled(pid):
            return Quota(State.DISABLED, detail="Quota checks disabled in settings", updated_at=now)
        return self.providers[pid].collect_quota(now)

    # -- results (main thread) ------------------------------------------
    def apply_local(self, pid: str, usage: LocalUsage) -> ProviderSnapshot:
        with self.lock:
            snap = self.snapshots[pid]
            snap.local = merge_local(snap.local, usage)
            return snap

    def apply_quota(self, pid: str, quota: Quota, now: float | None = None) -> ProviderSnapshot:
        now = now or time.time()
        with self.lock:
            snap = self.snapshots[pid]
            snap.quota = merge_quota(snap.quota, quota)
            interval = self.settings.quota_refresh_seconds
            if quota.state == State.RATE_LIMITED:
                interval = max(interval, RATE_LIMIT_BACKOFF)
            self.next_quota_at[pid] = now + interval
            return snap
