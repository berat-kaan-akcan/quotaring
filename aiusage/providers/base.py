"""Common provider interface and helpers for talking to provider CLIs."""

from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from ..jsonstore import read_json, write_json
from ..model import LocalUsage, Quota, State
from .. import paths

log = logging.getLogger(__name__)

# Set on application quit: stops retries and kills provider CLIs still running.
_shutdown = threading.Event()
_live: set = set()
_live_lock = threading.Lock()


def shutdown_children() -> None:
    _shutdown.set()
    with _live_lock:
        procs = list(_live)
    for p in procs:
        p.kill()


class QuotaError(Exception):
    """A classified quota failure. `detail` must never contain tokens or payloads."""

    def __init__(self, state: State, detail: str, transient: bool = False):
        super().__init__(detail)
        self.state = state
        self.detail = detail
        self.transient = transient


def classify_error_text(text: str) -> QuotaError:
    """Map a provider error message to a state, without echoing the message itself."""
    t = (text or "").lower()
    if "429" in t or "rate limit" in t or "rate_limit" in t or "too many requests" in t:
        return QuotaError(State.RATE_LIMITED, "Rate limited by provider (HTTP 429)", transient=False)
    if any(s in t for s in ("401", "403", "unauthor", "forbidden", "not logged in", "login",
                            "expired", "authentication", "oauth")):
        return QuotaError(State.NOT_AUTHENTICATED, "Not authenticated or login expired")
    if "timeout" in t or "timed out" in t:
        return QuotaError(State.UNAVAILABLE, "Provider timed out", transient=True)
    return QuotaError(State.UNAVAILABLE, "Provider query failed", transient=True)


def with_retries(fn: Callable[[], object], attempts: int = 3, base_delay: float = 1.0,
                 sleep: Callable[[float], None] = time.sleep):
    """Run fn; retry transient QuotaErrors with exponential backoff (1 s, 2 s, ...)."""
    for i in range(attempts):
        try:
            return fn()
        except QuotaError as e:
            if not e.transient or i == attempts - 1 or _shutdown.is_set():
                raise
            sleep(base_delay * (2 ** i))
    raise AssertionError("unreachable")


def find_executable(command: str) -> str | None:
    if not command:
        return None
    expanded = os.path.expanduser(command)
    if os.path.sep in expanded or (os.altsep and os.altsep in expanded):
        return expanded if os.path.isfile(expanded) else None
    found = shutil.which(expanded)
    if found:
        return found
    # GUI sessions often lack ~/.local/bin and similar on PATH.
    home = Path.home()
    names = [expanded + ext for ext in ((".cmd", ".exe", ".bat", "") if sys.platform == "win32" else ("",))]
    for d in (home / ".local" / "bin", home / ".npm-global" / "bin", home / "bin",
              Path("/usr/local/bin"), home / "AppData" / "Roaming" / "npm"):
        for n in names:
            p = d / n
            if p.is_file():
                return str(p)
    return None


class JsonLineProcess:
    """A child process spoken to with one JSON object per line on stdin/stdout.

    Reads happen on a helper thread so every wait has a deadline on all platforms.
    stderr is discarded: it may contain account details.
    """

    def __init__(self, argv: list[str], cwd: str | None = None):
        if _shutdown.is_set():
            raise QuotaError(State.UNAVAILABLE, "Shutting down")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(
            argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, creationflags=flags,
        )
        self.lines: queue.Queue = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        with _live_lock:
            _live.add(self)

    def kill(self) -> None:
        try:
            self.proc.kill()
        except OSError:
            pass

    def _pump(self):
        try:
            for line in self.proc.stdout:
                self.lines.put(line)
        except (OSError, ValueError):
            pass
        self.lines.put(None)

    def send(self, obj: dict) -> None:
        try:
            self.proc.stdin.write((json.dumps(obj) + "\n").encode())
            self.proc.stdin.flush()
        except (OSError, ValueError) as e:
            raise QuotaError(State.UNAVAILABLE, "Provider process closed its input", transient=True) from e

    def receive(self, deadline: float) -> dict:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise QuotaError(State.UNAVAILABLE, "Provider timed out", transient=True)
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty:
                continue
            if line is None:
                raise QuotaError(State.UNAVAILABLE, "Provider process exited", transient=True)
            try:
                msg = json.loads(line)
            except ValueError:
                continue  # non-JSON noise
            if isinstance(msg, dict):
                return msg

    def close(self) -> None:
        with _live_lock:
            _live.discard(self)
        if self.proc.poll() is None:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
            self.proc.terminate()
            try:
                self.proc.wait(2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


class Provider:
    """Base class. Subclasses implement `_collect_local` and `_collect_quota`.

    The public methods never raise: any unexpected error becomes an UNAVAILABLE state so
    one provider can never break the others or the UI.
    """

    id = "base"
    name = "Base"

    def __init__(self, settings):
        self.settings = settings

    # -- local activity -------------------------------------------------
    def collect_local(self, now: float) -> LocalUsage:
        try:
            usage = self._collect_local(now)
        except Exception as e:  # noqa: BLE001 - isolation boundary
            # Type name only: exception messages can quote file content.
            log.warning("%s: local collection failed (%s)", self.id, type(e).__name__)
            log.debug("traceback", exc_info=True)
            usage = LocalUsage(State.UNAVAILABLE, detail=f"Local collection failed ({type(e).__name__})")
        usage.updated_at = now
        return usage

    def _collect_local(self, now: float) -> LocalUsage:
        raise NotImplementedError

    # -- account quota --------------------------------------------------
    def collect_quota(self, now: float) -> Quota:
        try:
            quota = self._collect_quota(now)
        except QuotaError as e:
            quota = Quota(e.state, detail=e.detail)
        except Exception as e:  # noqa: BLE001 - isolation boundary
            log.warning("%s: quota collection failed (%s)", self.id, type(e).__name__)
            log.debug("traceback", exc_info=True)
            quota = Quota(State.UNAVAILABLE, detail=f"Quota query failed ({type(e).__name__})")
        quota.updated_at = now
        return quota

    def _collect_quota(self, now: float) -> Quota:
        return Quota(State.UNAVAILABLE, detail="No verified quota source")

    # -- scan cache -----------------------------------------------------
    def overlay_quota(self, quota: Quota, now: float) -> Quota:
        """Hook for newer limit evidence found by the local scan; default: unchanged."""
        return quota

    def scan_cache_path(self) -> Path:
        return paths.cache_dir() / f"scan-{self.id}-v1.json"

    def load_scan_cache(self) -> dict:
        data = read_json(self.scan_cache_path(), {})
        return data if isinstance(data, dict) else {}

    def save_scan_cache(self, data: dict) -> None:
        try:
            write_json(self.scan_cache_path(), data)
        except OSError:
            log.warning("%s: could not write scan cache", self.id)
