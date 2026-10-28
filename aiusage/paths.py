"""Platform-correct application directories and provider data locations."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "ai-usage-widget"
APP_DIR_NAME_WIN = "AIUsageWidget"


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


def antigravity_roots() -> list[Path]:
    """Directories that hold Antigravity `conversations/*.db` (IDE, CLI, desktop app)."""
    base = _home() / ".gemini"
    return [base / "antigravity-ide", base / "antigravity-cli", base / "antigravity"]
