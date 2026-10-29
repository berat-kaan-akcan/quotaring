"""Platform-correct application directories and provider data locations."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "quotaring"
APP_DIR_NAME_WIN = "QuotaRing"


def _home() -> Path:
    return Path(os.path.expanduser("~"))


def config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(_home() / "AppData" / "Roaming")
        return Path(base) / APP_DIR_NAME_WIN
    if sys.platform == "darwin":
        return _home() / "Library" / "Application Support" / APP_DIR_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME") or _home() / ".config") / APP_DIR_NAME


def cache_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(_home() / "AppData" / "Local")
        return Path(base) / APP_DIR_NAME_WIN / "Cache"
    if sys.platform == "darwin":
        return _home() / "Library" / "Caches" / APP_DIR_NAME
    return Path(os.environ.get("XDG_CACHE_HOME") or _home() / ".cache") / APP_DIR_NAME


def claude_home() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) if env else _home() / ".claude"


def codex_home() -> Path:
    env = os.environ.get("CODEX_HOME")
    return Path(env) if env else _home() / ".codex"


def antigravity_ide_state_dbs() -> list[Path]:
    """The Antigravity IDE's global state database (VS Code layout), newest product name first."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or _home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = _home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or _home() / ".config")
    return [base / name / "User" / "globalStorage" / "state.vscdb" for name in ("Antigravity IDE", "Antigravity")]


def antigravity_roots() -> list[Path]:
    """Directories that hold Antigravity `conversations/*.db` (IDE, CLI, desktop app)."""
    base = _home() / ".gemini"
    return [base / "antigravity-ide", base / "antigravity-cli", base / "antigravity"]
