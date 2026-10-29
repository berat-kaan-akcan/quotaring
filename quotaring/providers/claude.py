"""Claude Code: local JSONL transcripts + account limits via the CLI's `get_usage`."""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import replace

from .. import paths
from ..aggregate import aggregate, daily_totals, retention_cutoff
from ..model import LocalUsage, Quota, QuotaWindow, State, Tokens, UsageEvent
from ..scan import FileStates, as_int, list_files, parse_ts, read_new_lines
from .base import JsonLineProcess, Provider, QuotaError, classify_error_text, find_executable, with_retries

SCAN_VERSION = 2  # 2: also records rejected-request limit hits

# Limit names used by the CLI (get_usage keys and quotaLimits.rateLimitType).
LIMIT_WINDOWS = {"five_hour": ("5-hour session", 300), "seven_day": ("Weekly", 10080),
                 "seven_day_opus": ("Weekly · Opus", 10080), "seven_day_sonnet": ("Weekly · Sonnet", 10080)}


def parse_claude_line(obj: dict) -> tuple[str, list] | None:
    """Return (dedup key, [ts, model, input, output, cache_read, cache_write, reasoning])."""
    if obj.get("type") != "assistant" or obj.get("isApiErrorMessage"):
        return None
    msg = obj.get("message")
    if not isinstance(msg, dict):
        return None
    usage = msg.get("usage")
    if not isinstance(usage, dict):
        return None
    model = msg.get("model")
    if not isinstance(model, str) or not model or model == "<synthetic>":
        return None
    ts = parse_ts(obj.get("timestamp"))
    if ts is None:
        return None
    mid = msg.get("id")
    if not mid:
        return None
    key = f"{mid}:{obj.get('requestId') or ''}"
    details = usage.get("output_tokens_details")
    reasoning = as_int(details.get("thinking_tokens")) if isinstance(details, dict) else 0
    return key, [
        ts,
        model,
        as_int(usage.get("input_tokens")),
        as_int(usage.get("output_tokens")),
        as_int(usage.get("cache_read_input_tokens")),
        as_int(usage.get("cache_creation_input_tokens")),
        reasoning,
    ]


def parse_limit_hit(obj: dict) -> list | None:
    """[ts, limit name, resets_at] from the CLI's record of a request the provider rejected.

    Claude Code logs a synthetic assistant message with `quotaLimits` (status "rejected",
    rateLimitType, resetsAt epoch seconds) when an account limit blocks a request.
    """
    q = obj.get("quotaLimits")
    if not isinstance(q, dict) or q.get("status") != "rejected":
        return None
    ts = parse_ts(obj.get("timestamp"))
    kind, reset = q.get("rateLimitType"), q.get("resetsAt")
    if ts is None or not isinstance(kind, str) or not kind:
        return None
    if isinstance(reset, bool) or not isinstance(reset, (int, float)) or reset <= 0:
        return None
    return [ts, kind, float(reset)]


def latest_limit_hit(states: FileStates) -> list | None:
    hits = [e["limit"] for e in states.files.values() if isinstance(e.get("limit"), list)]
    return max(hits, key=lambda h: h[0]) if hits else None


def apply_limit_hit(quota: Quota, hit: list | None, now: float) -> Quota:
    """A rejected request is newer evidence than a polled percentage: show that limit as
    reached until its reset, even when the usage query lags, fails or is stale."""
    if not hit or hit[2] <= now:
        return quota
    if quota.state not in (State.OK, State.STALE, State.UNAVAILABLE, State.RATE_LIMITED, State.PENDING):
        return quota
    _ts, kind, reset = hit
    label, minutes = LIMIT_WINDOWS.get(kind, (kind, None))
    windows = list(quota.windows) if quota.state in (State.OK, State.STALE) else []
    for i, w in enumerate(windows):
        if w.key == kind:
            windows[i] = replace(w, used_percent=100.0, resets_at=reset, limited=True)
            break
    else:
        windows.insert(0, QuotaWindow(kind, label, 100.0, reset, minutes, limited=True))
    if quota.state in (State.OK, State.STALE):
        return replace(quota, windows=windows)
    return Quota(State.OK, windows, plan=quota.plan, source="Claude Code limit response (local log)",
                 documented=False, updated_at=hit[0])


def merge_record(old: list | None, new: list) -> list:
    """Streaming writes the same response several times with growing counts: keep the max."""
    if old is None:
        return new
    return [old[0], old[1]] + [max(a, b) for a, b in zip(old[2:], new[2:])]


def scan(states: FileStates, roots, now: float) -> bool:
    """Update `states` in place; return True when anything changed (cache needs saving)."""
    cutoff = retention_cutoff(now)
    found = list_files(roots, ".jsonl", cutoff)
    before = len(states.files)
    changed = False
    for path, entry in states.plan(found):
        changed = True
        try:
            lines, offset = read_new_lines(
                path, entry["offset"],
                lambda l: (b'"assistant"' in l and b'"usage"' in l) or b'"quotaLimits"' in l,
            )
        except OSError:
            continue  # retried next refresh: size/mtime stay stale
        events = entry["events"]
        for _off, obj in lines:
            hit = parse_limit_hit(obj)
            if hit and (not entry.get("limit") or hit[0] >= entry["limit"][0]):
                entry["limit"] = hit
            parsed = parse_claude_line(obj)
            if parsed:
                key, rec = parsed
                events[key] = merge_record(events.get(key), rec)
        for key in [k for k, r in events.items() if r[0] < cutoff]:
            del events[key]
        size, mtime = found[path]
        FileStates.done(entry, size, mtime, offset)
    return changed or len(states.files) != before


def dedup_events(states: FileStates) -> list[UsageEvent]:
    """Resumed and forked sessions copy earlier messages into new files: dedup globally."""
    merged: dict[str, list] = {}
    for entry in states.files.values():
        for key, rec in entry.get("events", {}).items():
            merged[key] = merge_record(merged.get(key), rec)
    return [
        UsageEvent(r[0], r[1], Tokens(input=r[2], output=r[3], cache_read=r[4], cache_write=r[5], reasoning=r[6]))
        for r in merged.values()
    ]


def windows_from_usage(payload: dict) -> tuple[list[QuotaWindow], dict]:
    rl = payload.get("rate_limits") or {}
    windows: list[QuotaWindow] = []
    for key, (label, minutes) in LIMIT_WINDOWS.items():
        w = rl.get(key)
        if not isinstance(w, dict):
            continue
        used = w.get("utilization")
        if isinstance(used, bool) or not isinstance(used, (int, float)):
            continue
        windows.append(QuotaWindow(key, label, max(0.0, min(100.0, float(used))),
                                   parse_ts(w.get("resets_at")), minutes))
    # Per-model weekly caps: "model_scoped" (CLI >= 2.1.31x) or "weekly_scoped" limits (older).
    for lim in rl.get("model_scoped") or []:
        if not isinstance(lim, dict):
            continue
        model, pct = lim.get("display_name"), lim.get("utilization")
        if (isinstance(model, str) and model and isinstance(pct, (int, float)) and not isinstance(pct, bool)
                and f"Weekly · {model}" not in {w.label for w in windows}):
            windows.append(QuotaWindow(f"weekly:{model}", f"Weekly · {model}",
                                       max(0.0, min(100.0, float(pct))), parse_ts(lim.get("resets_at")), 10080))
    for lim in rl.get("limits") or []:
        if not isinstance(lim, dict) or lim.get("kind") != "weekly_scoped":
            continue
        model = (((lim.get("scope") or {}).get("model") or {}).get("display_name"))
        pct = lim.get("percent")
        if (model and isinstance(pct, (int, float)) and not isinstance(pct, bool)
                and f"Weekly · {model}" not in {w.label for w in windows}):
            windows.append(QuotaWindow(f"weekly:{model}", f"Weekly · {model}",
                                       max(0.0, min(100.0, float(pct))), parse_ts(lim.get("resets_at")), 10080))
    extra = {}
    bd = rl.get("seven_day_breakdown")
    if isinstance(bd, dict) and isinstance(bd.get("rows"), list):
        rows = [
            {"key": r.get("key"), "label": r.get("display_name") or r.get("key"), "percent": float(r["percent"])}
            for r in bd["rows"]
            if isinstance(r, dict) and isinstance(r.get("percent"), (int, float)) and not isinstance(r.get("percent"), bool)
        ]
        if rows:
            extra["weekly_breakdown"] = rows
    return windows, extra


def native_install_binary() -> str | None:
    """Newest binary from Claude Code's native installer (~/.local/share/claude/versions/<ver>).

    Used when `claude` is not on PATH or its launcher symlink is broken.
    """
    from pathlib import Path

    versions = Path.home() / ".local" / "share" / "claude" / "versions"
    try:
        cands = [p for p in versions.iterdir() if p.is_file() and os.access(p, os.X_OK)]
    except OSError:
        return None

    def key(p):
        return [int(x) if x.isdigit() else 0 for x in p.name.split(".")]

    return str(max(cands, key=key)) if cands else None


class ClaudeProvider(Provider):
    id = "claude"
    name = "Claude Code"

    def __init__(self, settings, roots=None):
        super().__init__(settings)
        self.roots = roots
        self._states: FileStates | None = None
        self.limit_hit: list | None = None  # set by the local scan, read by overlay_quota

    def overlay_quota(self, quota: Quota, now: float) -> Quota:
        return apply_limit_hit(quota, self.limit_hit, now)

    def _roots(self):
        return self.roots if self.roots is not None else [paths.claude_home() / "projects"]

    def _collect_local(self, now: float) -> LocalUsage:
        roots = self._roots()
        if not any(r.is_dir() for r in roots):
            return LocalUsage(State.NOT_INSTALLED, source=str(roots[0]),
                              detail="No Claude Code history folder found")
        if self._states is None:
            data = self.load_scan_cache()
            self._states = FileStates(data if data.get("version") == SCAN_VERSION else None)
        if scan(self._states, roots, now):
            self.save_scan_cache({"version": SCAN_VERSION, **self._states.to_dict()})
        self.limit_hit = latest_limit_hit(self._states)
        events = dedup_events(self._states)
        return LocalUsage(State.OK, aggregate(events, now), source=str(roots[0]),
                          exact=True, files=len(self._states.files), daily=daily_totals(events, now))

    def _collect_quota(self, now: float) -> Quota:
        exe = find_executable(self.settings.claude_command)
        if not exe and self.settings.claude_command == "claude":
            exe = native_install_binary()
        if not exe:
            return Quota(State.NOT_INSTALLED, detail="`claude` CLI not found")
        payload = with_retries(lambda: self._query(exe), attempts=3)
        if payload.get("rate_limits_available") is not True:
            return Quota(State.UNSUPPORTED, plan=payload.get("subscription_type"),
                         detail="No subscription limits for this account (API key or unsupported plan)")
        if payload.get("rate_limits") is None:
            return Quota(State.UNAVAILABLE, detail="Usage endpoint returned no data")
        windows, extra = windows_from_usage(payload)
        if not windows:
            return Quota(State.UNAVAILABLE, detail="Usage response had no limit windows")
        plan = payload.get("subscription_type")
        return Quota(State.OK, windows, plan=plan.capitalize() if isinstance(plan, str) else None,
                     source="claude CLI get_usage (experimental, undocumented)", documented=False,
                     extra=extra)

    def _query(self, exe: str) -> dict:
        timeout = self.settings.timeout_seconds
        # Empty cwd + safe mode: no project hooks, tools or settings are loaded. No model turn.
        with tempfile.TemporaryDirectory(prefix="quotaring-") as cwd:
            proc = JsonLineProcess([
                exe, "--safe-mode", "--print", "--verbose",
                "--input-format", "stream-json", "--output-format", "stream-json",
                "--no-session-persistence", "--permission-mode", "dontAsk", "--tools", "",
            ], cwd=cwd)
            try:
                deadline = time.monotonic() + timeout
                init = self._request(proc, "initialize", deadline)
                if ((init.get("account") or {}).get("tokenSource")) == "none":
                    raise QuotaError(State.NOT_AUTHENTICATED, "Claude Code is not logged in")
                return self._request(proc, "get_usage", deadline, skip_behaviors=True)
            finally:
                proc.close()

    @staticmethod
    def _request(proc: JsonLineProcess, kind: str, deadline: float, **params) -> dict:
        proc.send({"type": "control_request", "request_id": kind,
                   "request": {"subtype": kind, **params}})
        while True:
            msg = proc.receive(deadline)
            if msg.get("type") == "control_request":
                raise QuotaError(State.UNAVAILABLE, "Unexpected permission request from CLI")
            resp = msg.get("response") or {}
            if msg.get("type") == "control_response" and resp.get("request_id") == kind:
                if resp.get("subtype") != "success":
                    err = str(resp.get("error") or "")
                    if "unsupported control request" in err.lower():
                        raise QuotaError(State.UNSUPPORTED, "This Claude Code version has no usage query")
                    raise classify_error_text(err)
                body = resp.get("response")
                if not isinstance(body, dict):
                    raise QuotaError(State.UNAVAILABLE, "Malformed usage response")
                return body
