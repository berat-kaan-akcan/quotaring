"""Shared fixtures. All data here is synthetic; tests never touch real provider folders."""

from __future__ import annotations

import json
import os
import stat
import sys
import textwrap
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quotaring.settings import Settings  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Point config/cache/home at a temp dir so tests cannot read or write real data."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    # A running Antigravity is found by process, not by folder: never ask the real one.
    monkeypatch.setattr("quotaring.providers.antigravity.running_servers", lambda: [])
    # Prices: the built-in table unless a test loads a list; never the network.
    monkeypatch.setattr("quotaring.pricing._remote", None)
    monkeypatch.setattr("quotaring.pricing._fetched_at", None)
    monkeypatch.setattr("quotaring.pricing.REMOTE_URL", "http://127.0.0.1:9/litellm")
    monkeypatch.setattr("quotaring.pricing.OPENROUTER_URL", "http://127.0.0.1:9/openrouter")
    monkeypatch.setattr("quotaring.updater.API_URL", "http://127.0.0.1:9/releases")
    return tmp_path


@pytest.fixture
def settings():
    return Settings(timeout_seconds=5)


def iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts)) + ".000Z"


def write_jsonl(path: Path, objs, trailing_partial: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for o in objs:
            f.write((o if isinstance(o, str) else json.dumps(o)) + "\n")
        if trailing_partial:
            f.write(trailing_partial)
    return path


def fake_cli(tmp_path: Path, name: str, body: str) -> str:
    """Create an executable Python script that imitates a provider CLI."""
    script = tmp_path / "bin" / name
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(f"#!{sys.executable}\n" + textwrap.dedent(body), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    if os.name == "nt":  # pragma: no cover - CI on Windows would need a .cmd wrapper
        cmd = script.with_suffix(".cmd")
        cmd.write_text(f'@"{sys.executable}" "{script}" %*\n')
        return str(cmd)
    return str(script)
