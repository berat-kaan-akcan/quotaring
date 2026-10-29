"""Google Antigravity: per-conversation SQLite databases with protobuf blobs.

Schema (recovered from descriptors embedded in the `agy` binary):
  gen_metadata.data  = CortexStepGeneratorMetadata {1 chat_model, 2 step_indices}
  ChatModelMetadata  = {4 usage: ModelUsageStats, 19 response_model, 21 model_display_name}
  ModelUsageStats    = {2 input_tokens, 3 output_tokens, 4 cache_write_tokens,
                        5 cache_read_tokens, 9 thinking_output_tokens}
  steps.metadata     = CortexStepMetadata {1 created_at: Timestamp{1 seconds}}
This is an undocumented internal format. Databases are opened read-only; anything that does
not parse is skipped.

Quota: the IDE caches the language server's GetUserStatus reply in its VS Code state database
(`ItemTable` key `antigravityUnifiedStateSync.userStatus`, base64 of a sentinel-keyed protobuf
whose value is base64 of UserStatus). Only these fields are read:
  UserStatus.33 cascade_model_config_data .1 client_model_configs[] =
      {1 label, 15 quota_info: {1 remaining_fraction: float, 2 reset_time: Timestamp{1 seconds}}}
  UserStatus.36 user_tier = {2 name}
The same table holds the account's OAuth token and the record holds name and email; neither
is read or kept — the query selects this one key and only the fields above are decoded.

That cache only has one value per model. While Antigravity runs, its `agy --hub` language
server answers on 127.0.0.1 (port and CSRF token are on its command line); its
RetrieveUserQuotaSummary reply is what the "View Usage" panel shows: groups ("Gemini Models",
"Claude and GPT models", "Gemini 4 Argon") of buckets {window: "5h" | "weekly",
remainingFraction, resetTime}. That is preferred; the IDE cache is the fallback. Its
GetUserStatus reply lists the models (only their labels are read); each is matched to its group
through the group's name or its "Models within this group: Claude Opus, ..." description, so the
popup can show models one by one while the limits stay one per group.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import sqlite3
import struct
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

from .. import paths, protowire as pw
from ..aggregate import aggregate, daily_totals
from ..model import LocalUsage, Quota, QuotaWindow, State, Tokens, UsageEvent
from .base import Provider

log = logging.getLogger(__name__)
SCAN_VERSION = 1
USER_STATUS_KEY = "antigravityUnifiedStateSync.userStatus"
# The IDE refreshes the cache while it runs; older than this, the values are shown as stale.
QUOTA_STALE_AFTER = 6 * 3600
QUOTA_SUMMARY_PATH = "/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary"
USER_STATUS_PATH = "/exa.language_server_pb.LanguageServerService/GetUserStatus"
BUCKET_WINDOWS = {"5h": ("5-hour session", 300), "weekly": ("Weekly", 10080)}


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


def read_user_status(db: Path) -> bytes | None:
    """The cached UserStatus protobuf, or None. Reads only that one key."""
    try:
        con = connect_ro(db)
        try:
            row = con.execute("SELECT value FROM ItemTable WHERE key = ?", (USER_STATUS_KEY,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    if not row or not row[0]:
        return None
    try:
        outer = pw.parse(base64.b64decode(row[0]))
        for entry in outer.get(1, []):
            value = pw.submessage(pw.parse(entry), 2)
            inner = pw.first(value, 1) if value else None
            if isinstance(inner, (bytes, bytearray)):
                return base64.b64decode(inner)
    except (ValueError, TypeError):
        return None
    return None


def _family(label: str) -> str:
    """'Claude Opus 5.5 (High)' -> 'Claude Opus 5.5': variants of one model share a quota."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", label).strip() or label


def parse_user_status(blob: bytes) -> tuple[list[QuotaWindow], str | None]:
    """Per-model-family limit windows (tightest variant, earliest reset) and the plan name."""
    msg = pw.parse(blob)
    tier = pw.submessage(msg, 36)
    plan = None
    if tier:
        name = pw.first(tier, 2)
        plan = name.decode("utf-8", "replace") if isinstance(name, (bytes, bytearray)) else None
    families: dict[str, list] = {}  # family -> [remaining, reset]; insertion order = IDE order
    config = pw.submessage(msg, 33)
    for raw in (config or {}).get(1, []):
        if not isinstance(raw, (bytes, bytearray)):
            continue
        model = pw.parse(raw)
        label, quota = pw.first(model, 1), pw.submessage(model, 15)
        if not isinstance(label, (bytes, bytearray)) or quota is None:
            continue
        frac = pw.first(quota, 1)
        if not isinstance(frac, (bytes, bytearray)) or len(frac) != 4:
            continue
        remaining = max(0.0, min(1.0, struct.unpack("<f", frac)[0]))
        reset_ts = pw.submessage(quota, 2)
        reset = pw.first(reset_ts, 1) if reset_ts else None
        reset = float(reset) if isinstance(reset, int) and reset > 0 else None
        fam = _family(label.decode("utf-8", "replace"))
        prev = families.get(fam)
        if prev is None:
            families[fam] = [remaining, reset]
        else:
            prev[0] = min(prev[0], remaining)
            if reset is not None and (prev[1] is None or reset < prev[1]):
                prev[1] = reset
    windows = [QuotaWindow(f"antigravity:{fam}", fam, round((1 - rem) * 100, 1), reset)
               for fam, (rem, reset) in families.items()]
    return windows, plan


def _server_args(argv: list[str]) -> tuple[int, str] | None:
    """(port, csrf token) from an `agy --hub` command line, else None."""
    if not argv or not re.match(r"(agy|language_server)", os.path.basename(argv[0])):
        return None
    opts = dict(a[2:].split("=", 1) for a in argv[1:] if a.startswith("--") and "=" in a)
    port, token = opts.get("hub-port", ""), opts.get("csrf_token", "")
    return (int(port), token) if port.isdigit() and token else None


def running_servers() -> list[tuple[int, str]]:
    """This user's Antigravity language servers that accept quota requests (Linux and macOS)."""
    return [s for s in map(_server_args, own_cmdlines()) if s]


def own_cmdlines() -> list[list[str]]:
    """Command lines of this user's processes. Another user's process could pose as a language
    server and feed made-up limits, so only our own count."""
    cmdlines: list[list[str]] = []
    if sys.platform.startswith("linux"):
        uid = os.getuid()
        for d in Path("/proc").glob("[0-9]*"):
            try:
                if d.stat().st_uid != uid:
                    continue
                cmdlines.append((d / "cmdline").read_bytes().decode("utf-8", "replace").split("\0"))
            except OSError:
                continue  # exited meanwhile
    elif sys.platform == "darwin":
        try:
            out = subprocess.run(["ps", "-U", str(os.getuid()), "-ww", "-o", "args="],
                                 capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        cmdlines = [line.split() for line in out.splitlines()]
    return cmdlines


def fetch(port: int, token: str, path: str) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json", "X-Codeium-Csrf-Token": token})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never via a proxy
    with opener.open(req, timeout=3) as r:
        return json.loads(r.read())


def _epoch(iso) -> float | None:
    if not isinstance(iso, str):
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _groups(data) -> list[dict]:
    groups = (data.get("response") or {}).get("groups") if isinstance(data, dict) else None
    return [g for g in groups if isinstance(g, dict)] if isinstance(groups, list) else []


def _plain(text: str) -> str:
    """Names from the server end up in Qt labels and tooltips: no markup."""
    return re.sub(r"[<>&]", "", text)


def _group_name(group: dict) -> str:
    return re.sub(r"\s+models$", "", _plain(str(group.get("displayName") or "")), flags=re.I).strip()


def parse_quota_summary(data: dict) -> list[QuotaWindow]:
    """'Gemini Models' 5h/weekly buckets -> '5-hour session · Gemini', 'Weekly · Gemini', ..."""
    windows = []
    for group in _groups(data):
        name = _group_name(group)
        buckets = [b for b in group.get("buckets") or [] if isinstance(b, dict) and b.get("window") in BUCKET_WINDOWS]
        buckets.sort(key=lambda b: BUCKET_WINDOWS[b["window"]][1])  # 5 hours before weekly
        for b in buckets:
            frac = b.get("remainingFraction", 0.0)  # proto3 JSON omits zero
            if not isinstance(frac, (int, float)) or not name:
                continue
            label, minutes = BUCKET_WINDOWS[b["window"]]
            windows.append(QuotaWindow(f"antigravity:{b.get('bucketId') or name + ':' + b['window']}",
                                       f"{label} · {name}", round((1 - max(0.0, min(1.0, frac))) * 100, 1),
                                       _epoch(b.get("resetTime")), minutes))
    return windows


def model_families(status: dict) -> list[str]:
    """Model families in the IDE's order from a GetUserStatus reply; nothing else is read."""
    configs = (((status or {}).get("userStatus") or {}).get("cascadeModelConfigData") or {}).get("clientModelConfigs")
    out: list[str] = []
    for c in configs if isinstance(configs, list) else []:
        label = c.get("label") if isinstance(c, dict) else None
        if isinstance(label, str) and _family(_plain(label)) not in out:
            out.append(_family(_plain(label)))
    return out


def group_models(families: list[str], data: dict, windows: list[QuotaWindow]) -> list[dict]:
    """[{"name": "Claude Opus 5.5", "windows": [5h key, weekly key]}, ...] for models with a group."""
    groups = []
    for group in _groups(data):
        name = _group_name(group)
        keys = [w.key for w in windows if w.label.endswith(f" · {name}")]
        m = re.search(r"within this group:\s*(.+)", str(group.get("description") or ""), re.I)
        members = [set(x.lower().split()) for x in m.group(1).rstrip(". ").split(",")] if m else []
        if name and keys:
            groups.append((name, members, keys))
    out = []
    for fam in families:
        words = set(fam.lower().split())
        # Its own group ("Gemini 4 Argon") first, then a listed member whose words it has ("Gemini Flash").
        hit = next((g for g in groups if g[0].lower() == fam.lower()), None) or \
            next((g for g in groups if any(mem and mem <= words for mem in g[1])), None)
        if hit:
            out.append({"name": fam, "windows": hit[2]})
    return out


class AntigravityProvider(Provider):
    id = "antigravity"
    name = "Antigravity"

    def __init__(self, settings, roots=None, state_dbs=None, servers=None):
        super().__init__(settings)
        self.roots = roots
        self.state_dbs = state_dbs
        self.servers = servers
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

    def _live_quota(self) -> tuple[list[QuotaWindow], list[dict]]:
        """Group limits and the models in each, from a running language server."""
        for port, token in self.servers if self.servers is not None else running_servers():
            try:
                summary = fetch(port, token, QUOTA_SUMMARY_PATH)
                windows = parse_quota_summary(summary)
                if not windows:
                    continue
                families = model_families(fetch(port, token, USER_STATUS_PATH))
            except (OSError, ValueError) as e:
                log.info("antigravity: quota from port %s failed (%s)", port, type(e).__name__)
                continue
            return windows, group_models(families, summary, windows)
        return [], []

    def _collect_quota(self, now: float) -> Quota:
        dbs = [p for p in (self.state_dbs if self.state_dbs is not None else paths.antigravity_ide_state_dbs())
               if p.is_file()]
        live, models = self._live_quota()
        if live:
            blob = read_user_status(max(dbs, key=os.path.getmtime)) if dbs else None
            plan = parse_user_status(blob)[1] if blob else None  # the summary carries no plan name
            return Quota(State.OK, live, plan=plan, source="Antigravity (running)", updated_at=now,
                         extra={"models": models} if models else {})
        if not dbs:
            return Quota(State.UNAVAILABLE, source="none",
                         detail="Open the Antigravity IDE once: it stores the account limits locally")
        db = max(dbs, key=os.path.getmtime)
        blob = read_user_status(db)
        if blob is None:
            return Quota(State.UNAVAILABLE, source="Antigravity IDE",
                         detail="Antigravity IDE has not stored the account limits yet")
        windows, plan = parse_user_status(blob)
        if not windows:
            return Quota(State.UNSUPPORTED, plan=plan, source="Antigravity IDE")
        written = os.path.getmtime(db)
        stale = now - written > QUOTA_STALE_AFTER
        return Quota(State.STALE if stale else State.OK, windows, plan=plan, source="Antigravity IDE (local cache)",
                     detail="Open the Antigravity IDE to refresh its limits" if stale else "",
                     updated_at=written)
