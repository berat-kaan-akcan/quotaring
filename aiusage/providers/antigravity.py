"""Google Antigravity: per-conversation SQLite databases with protobuf blobs.

Schema (recovered from descriptors embedded in the `agy` binary, see RESEARCH.md):
  gen_metadata.data  = CortexStepGeneratorMetadata {1 chat_model, 2 step_indices}
  ChatModelMetadata  = {4 usage: ModelUsageStats, 19 response_model, 21 model_display_name}
  ModelUsageStats    = {2 input_tokens, 3 output_tokens, 4 cache_write_tokens,
                        5 cache_read_tokens, 9 thinking_output_tokens}
  steps.metadata     = CortexStepMetadata {1 created_at: Timestamp{1 seconds}}
This is an undocumented internal format. Databases are opened read-only; anything that does
not parse is skipped.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

from .. import paths, protowire as pw
from ..aggregate import aggregate, daily_totals
from ..model import LocalUsage, Quota, State, Tokens, UsageEvent
from .base import Provider

log = logging.getLogger(__name__)
SCAN_VERSION = 1


def connect_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=2)


def _signature(path: Path) -> list:
    sig = []
    for p in (path, Path(str(path) + "-wal")):
        try:
            st = os.stat(p)
            sig += [st.st_size, st.st_mtime]
        except OSError:
            sig += [None, None]
    return sig


def _step_time(blob) -> float | None:
    if not isinstance(blob, (bytes, bytearray)) or not blob:
        return None
    try:
        meta = pw.parse(blob)
        ts = pw.submessage(meta, 1)
    except ValueError:
        return None
    if not ts:
        return None
    secs = pw.first(ts, 1)
    return float(secs) if isinstance(secs, int) and secs > 0 else None


def _text(v) -> str | None:
    if isinstance(v, (bytes, bytearray)):
        try:
            s = v.decode("utf-8").strip()
        except UnicodeDecodeError:
            return None
        return s or None
    return None


def parse_generation(blob) -> tuple[str, list[int], list[int]] | None:
    """Return (model, [input, output, cache_read, cache_write, reasoning], step_indices)."""
    if not isinstance(blob, (bytes, bytearray)) or not blob:
        return None
    try:
        gen = pw.parse(blob)
        chat = pw.submessage(gen, 1)
        if not chat:
            return None
        usage = pw.submessage(chat, 4)
        if not usage:
            return None
        steps = pw.packed_varints(gen, 2)
    except ValueError:
        return None

    def num(f):
        v = pw.first(usage, f, 0)
        return v if isinstance(v, int) and v >= 0 else 0

    comps = [num(2), num(3), num(5), num(4), num(9)]
    if not any(comps):
        return None
    model = _text(pw.first(chat, 19)) or _text(pw.first(chat, 21)) or "unknown"
    return model, comps, steps


def read_conversation(path: Path) -> list[list]:
    """Return [[ts|None, model, input, output, cache_read, cache_write, reasoning], ...]."""
    con = connect_ro(path)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "gen_metadata" not in tables:
            return []
        step_times: dict[int, float] = {}
        if "steps" in tables:
            for idx, meta in con.execute("SELECT idx, metadata FROM steps"):
                t = _step_time(meta)
                if t is not None and isinstance(idx, int):
                    step_times[idx] = t
        out = []
        for _idx, data in con.execute("SELECT idx, data FROM gen_metadata ORDER BY idx"):
            parsed = parse_generation(data)
            if not parsed:
                continue
            model, comps, steps = parsed
            times = [step_times[s] for s in steps if s in step_times]
            out.append([min(times) if times else None, model, *comps])
        return out
    finally:
        con.close()


class AntigravityProvider(Provider):
    id = "antigravity"
    name = "Antigravity"

    def __init__(self, settings, roots=None):
        super().__init__(settings)
        self.roots = roots
        self._cache: dict | None = None

    def _roots(self) -> list[Path]:
        return self.roots if self.roots is not None else paths.antigravity_roots()

    def _collect_local(self, now: float) -> LocalUsage:
        conv_dirs = [r / "conversations" for r in self._roots() if (r / "conversations").is_dir()]
        if not conv_dirs:
            return LocalUsage(State.NOT_INSTALLED, source=str(self._roots()[0]),
                              detail="No Antigravity conversation folder found")
        if self._cache is None:
            data = self.load_scan_cache()
            self._cache = data.get("dbs", {}) if data.get("version") == SCAN_VERSION else {}
        seen: dict[str, tuple[float, str]] = {}  # conversation id -> (mtime, path); newest copy wins
        for d in conv_dirs:
            for db in d.glob("*.db"):
                try:
                    mtime = os.path.getmtime(db)
                except OSError:
                    continue  # deleted between listing and stat
                prev = seen.get(db.stem)
                if prev is None or mtime > prev[0]:
                    seen[db.stem] = (mtime, str(db))
        live = {p for _m, p in seen.values()}
        changed = False
        for p in list(self._cache):
            if p not in live:
                del self._cache[p]
                changed = True
        failed = 0
        for p in live:
            sig = _signature(Path(p))
            entry = self._cache.get(p)
            if entry and entry.get("sig") == sig:
                continue
            try:
                self._cache[p] = {"sig": sig, "events": read_conversation(Path(p))}
                changed = True
            except (sqlite3.Error, OSError) as e:
                failed += 1
                log.warning("antigravity: skipped unreadable database %s (%s)", p, type(e).__name__)
        if changed:
            self.save_scan_cache({"version": SCAN_VERSION, "dbs": self._cache})
        events = [
            UsageEvent(r[0], r[1], Tokens(input=r[2], output=r[3], cache_read=r[4], cache_write=r[5], reasoning=r[6]))
            for e in self._cache.values() for r in e["events"]
        ]
        detail = f"{failed} database(s) could not be read" if failed else ""
        return LocalUsage(State.OK, aggregate(events, now), source=str(conv_dirs[0].parent.parent),
                          exact=True, files=len(live), detail=detail, daily=daily_totals(events, now))

    def _collect_quota(self, now: float) -> Quota:
        return Quota(State.UNAVAILABLE, source="none",
                     detail="No documented quota source for Antigravity")
