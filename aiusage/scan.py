"""Incremental reading of append-only JSONL logs.

Each file is remembered by size, mtime and the byte offset reached last time, so a refresh
only parses lines appended since the previous scan. A file that shrank is re-read from the
start. A trailing partial line is left for the next scan.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

log = logging.getLogger(__name__)


def parse_ts(value) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.timestamp()


def as_int(value) -> int:
    """Non-negative integer or 0; tolerates missing, null, bool and garbage values."""
    if isinstance(value, bool) or value is None:
        return 0
    try:
        n = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return n if n > 0 else 0


def list_files(roots: list[Path], suffix: str, min_mtime: float) -> dict[str, tuple[int, float]]:
    found: dict[str, tuple[int, float]] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for dirpath, _dirs, names in os.walk(root):
            for n in names:
                if not n.endswith(suffix):
                    continue
                p = os.path.join(dirpath, n)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if st.st_mtime >= min_mtime:
                    found[p] = (st.st_size, st.st_mtime)
    return found


def read_new_lines(
    path: str, offset: int, wanted: Callable[[bytes], bool]
) -> tuple[list[tuple[int, dict]], int]:
    """Return ([(line_offset, parsed_json)], new_offset) for complete new lines."""
    out: list[tuple[int, dict]] = []
    with open(path, "rb") as f:
        f.seek(offset)
        for line in f:
            if not line.endswith(b"\n"):
                break
            start = offset
            offset += len(line)
            if not wanted(line):
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                out.append((start, obj))
    return out, offset


class FileStates:
    """Per-file bookkeeping for incremental scans, persisted by the owning provider."""

    def __init__(self, data: dict | None = None):
        self.files: dict[str, dict] = {}
        if isinstance(data, dict) and isinstance(data.get("files"), dict):
            self.files = data["files"]

    def plan(self, found: dict[str, tuple[int, float]]) -> Iterator[tuple[str, dict]]:
        """Yield (path, entry) for files needing a (partial) re-read; forget vanished files."""
        for p in list(self.files):
            if p not in found:
                del self.files[p]
        for p, (size, mtime) in found.items():
            entry = self.files.get(p)
            if entry and entry.get("size") == size and entry.get("mtime") == mtime:
                continue
            if not entry or size < entry.get("offset", 0):
                entry = self.files[p] = {"offset": 0, "size": -1, "mtime": 0, "state": {}, "events": {}}
            yield p, entry

    @staticmethod
    def done(entry: dict, size: int, mtime: float, offset: int) -> None:
        entry["offset"] = offset
        entry["size"] = size
        entry["mtime"] = mtime

    def to_dict(self) -> dict:
        return {"files": self.files}
