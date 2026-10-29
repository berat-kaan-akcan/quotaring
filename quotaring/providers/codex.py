"""OpenAI Codex CLI: local rollout logs + ChatGPT-plan limits via `codex app-server`.

Only ChatGPT-plan rate limits are shown as quota. API-key accounts have no plan quota and
are reported as unsupported; API billing is never mixed in.
"""

from __future__ import annotations

import time

from .. import __version__, paths
from ..aggregate import aggregate, daily_totals, retention_cutoff
from ..model import LocalUsage, Quota, QuotaWindow, State, Tokens, UsageEvent
from ..scan import FileStates, as_int, list_files, parse_ts, read_new_lines
from .base import JsonLineProcess, Provider, QuotaError, classify_error_text, find_executable, with_retries

SCAN_VERSION = 1
COMPONENTS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")


def _vec(u) -> list[int] | None:
    if not isinstance(u, dict):
        return None
    return [as_int(u.get(k)) for k in COMPONENTS]


def _record(ts: float, model: str, v: list[int]) -> list:
    inp, cached, out, reasoning = v
    # Codex reports input including cached input; split them so totals are not doubled.
    return [ts, model, max(0, inp - cached), out, min(cached, inp) if inp else cached, 0, reasoning]


def parse_codex_lines(lines, state: dict) -> dict[str, list]:
    """Turn rollout events into {key: record}. `state` carries model/counters across scans.

    Two formats are handled:
    - `token_usage_record` (newer): one record per response, keyed by response_id.
    - `token_count` (older): cumulative `total_token_usage`; usage is the delta from the
      previous event. A file's first event counts only `last_token_usage`, because forked or
      resumed sessions start from the parent's running total.
    Once a file shows `token_usage_record`, `token_count` events in it are ignored.
    """
    out: dict[str, list] = {}
    for off, obj in lines:
        typ = obj.get("type")
        p = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        kind = p.get("type") if typ == "event_msg" else typ
        if kind == "turn_context" or typ == "turn_context":
            if isinstance(p.get("model"), str) and p["model"]:
                state["model"] = p["model"]
            continue
        ts = parse_ts(obj.get("timestamp"))
        if ts is None:
            continue
        model = state.get("model") or "unknown"
        if kind == "token_usage_record":
            v = _vec(p.get("usage"))
            rid = p.get("response_id")
            if v and rid and any(v):
                state["modern"] = True
                out[f"r:{rid}"] = _record(ts, model, v)
            continue
        if kind != "token_count" or state.get("modern"):
            continue
        info = p.get("info") if isinstance(p.get("info"), dict) else {}
        cur = _vec(info.get("total_token_usage"))
        if cur is None:
            continue
        prev = state.get("prev")
        state["prev"] = cur
        if prev is not None and cur == prev:
            continue  # repeated event
        if prev is not None and all(c >= q for c, q in zip(cur, prev)):
            delta = [c - q for c, q in zip(cur, prev)]
        else:
            delta = _vec(info.get("last_token_usage")) or [0, 0, 0, 0]
        if any(delta):
            out[f"o:{off}"] = _record(ts, model, delta)
    return out


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
                lambda l: b"token_count" in l or b"turn_context" in l or b"token_usage_record" in l,
            )
        except OSError:
            continue
        entry["events"].update(parse_codex_lines(lines, entry["state"]))
        for key in [k for k, r in entry["events"].items() if r[0] < cutoff]:
            del entry["events"][key]
        size, mtime = found[path]
        FileStates.done(entry, size, mtime, offset)
    return changed or len(states.files) != before


def events_of(states: FileStates) -> list[UsageEvent]:
    seen: dict[str, list] = {}
    for path, entry in states.files.items():
        for key, r in entry.get("events", {}).items():
            # response ids are global; offset keys are per file
            seen[key if key.startswith("r:") else f"{path}:{key}"] = r
    return [UsageEvent(r[0], r[1], Tokens(input=r[2], output=r[3], cache_read=r[4], cache_write=r[5], reasoning=r[6]))
            for r in seen.values()]


def windows_from_rate_limits(payload: dict) -> tuple[list[QuotaWindow], str | None]:
    buckets = payload.get("rateLimitsByLimitId")
    if not isinstance(buckets, dict) or not buckets:
        buckets = {"codex": payload.get("rateLimits") or {}}
    windows: list[QuotaWindow] = []
    plan = None
    for bid, bucket in buckets.items():
        if not isinstance(bucket, dict):
            continue
        plan = plan or bucket.get("planType")
        name = bucket.get("limitName") or ("" if bid == "codex" else str(bid))
        for slot in ("primary", "secondary"):
            w = bucket.get(slot)
            if not isinstance(w, dict):
                continue
            used = w.get("usedPercent")
            if isinstance(used, bool) or not isinstance(used, (int, float)):
                continue
            mins = w.get("windowDurationMins")
            mins = int(mins) if isinstance(mins, (int, float)) and not isinstance(mins, bool) and mins > 0 else None
            if mins is None:
                label = slot.capitalize()
            elif mins <= 6 * 60:
                label = f"{round(mins / 60)}-hour session" if mins >= 60 else f"{mins}-minute"
            elif mins >= 6 * 1440:
                label = "Weekly"
            else:
                label = f"{round(mins / 1440)}-day"
            if name:
                label = f"{label} · {name}"
            resets = w.get("resetsAt")
            resets = float(resets) if isinstance(resets, (int, float)) and not isinstance(resets, bool) and resets > 0 else None
            windows.append(QuotaWindow(f"{bid}:{slot}", label, max(0.0, min(100.0, float(used))), resets, mins))
    return windows, plan


class CodexProvider(Provider):
    id = "codex"
    name = "Codex"

    def __init__(self, settings, roots=None):
        super().__init__(settings)
        self.roots = roots
        self._states: FileStates | None = None

    def _roots(self):
        if self.roots is not None:
            return self.roots
        home = paths.codex_home()
        return [home / "sessions", home / "archived_sessions"]

    def _collect_local(self, now: float) -> LocalUsage:
        roots = self._roots()
        if not any(r.is_dir() for r in roots):
            return LocalUsage(State.NOT_INSTALLED, source=str(roots[0]),
                              detail="No Codex session folder found")
        if self._states is None:
            data = self.load_scan_cache()
            self._states = FileStates(data if data.get("version") == SCAN_VERSION else None)
        if scan(self._states, roots, now):
            self.save_scan_cache({"version": SCAN_VERSION, **self._states.to_dict()})
        events = events_of(self._states)
        return LocalUsage(State.OK, aggregate(events, now), source=str(roots[0]),
                          exact=True, files=len(self._states.files), daily=daily_totals(events, now))

    def _collect_quota(self, now: float) -> Quota:
        exe = find_executable(self.settings.codex_command)
        if not exe:
            return Quota(State.NOT_INSTALLED, detail="`codex` CLI not found")
        account, payload = with_retries(lambda: self._query(exe), attempts=3)
        acct = account.get("account") if isinstance(account.get("account"), dict) else None
        if acct is None:
            return Quota(State.NOT_AUTHENTICATED, detail="Codex is not logged in")
        if acct.get("type") != "chatgpt":
            return Quota(State.UNSUPPORTED, detail="API-key account: no ChatGPT plan limits (API billing not shown)")
        windows, plan = windows_from_rate_limits(payload)
        plan = plan or acct.get("planType")
        if not windows:
            return Quota(State.UNAVAILABLE, plan=plan, detail="No active limit windows reported")
        return Quota(State.OK, windows, plan=str(plan).capitalize() if plan else None,
                     source="codex app-server account/rateLimits/read", documented=True)

    def _query(self, exe: str) -> tuple[dict, dict]:
        proc = JsonLineProcess([exe, "app-server"])
        try:
            deadline = time.monotonic() + self.settings.timeout_seconds
            self._request(proc, 1, "initialize", {
                "clientInfo": {"name": "quotaring", "title": "QuotaRing", "version": __version__},
            }, deadline)
            proc.send({"method": "initialized"})
            account = self._request(proc, 2, "account/read", {"refreshToken": False}, deadline)
            acct = account.get("account") if isinstance(account.get("account"), dict) else None
            if acct is None or acct.get("type") != "chatgpt":
                return account, {}
            return account, self._request(proc, 3, "account/rateLimits/read", {}, deadline)
        finally:
            proc.close()

    @staticmethod
    def _request(proc: JsonLineProcess, rid: int, method: str, params: dict, deadline: float) -> dict:
        proc.send({"id": rid, "method": method, "params": params})
        while True:
            msg = proc.receive(deadline)
            if msg.get("id") != rid:
                continue  # notifications
            if "error" in msg:
                err = msg.get("error") or {}
                raise classify_error_text(f"{err.get('code', '')} {err.get('message', '')}")
            res = msg.get("result")
            if not isinstance(res, dict):
                raise QuotaError(State.UNAVAILABLE, "Malformed app-server response")
            return res
