"""User settings, persisted as JSON in the platform config directory."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import paths
from .jsonstore import read_json, write_json

PROVIDER_IDS = ("claude", "codex", "antigravity")


@dataclass
class Settings:
    local_refresh_seconds: int = 60
    quota_refresh_seconds: int = 300
    timeout_seconds: int = 20
    theme: str = "system"  # system | light | dark
    language: str = "system"  # system | en | tr
    opacity: float = 0.96
    always_on_top: bool = True
    start_at_login: bool = False
    expanded: bool = False
    period: str = "today"  # period shown in the expanded breakdown
    minimize_to_tray: bool = True
    notify_threshold: int = 90  # percent; 0 disables quota notifications
    providers_enabled: dict = field(default_factory=lambda: {p: True for p in PROVIDER_IDS})
    quota_enabled: dict = field(default_factory=lambda: {p: True for p in PROVIDER_IDS})
    claude_command: str = "claude"
    codex_command: str = "codex"
    window: dict = field(default_factory=dict)  # x, y, w, h

    def clamp(self) -> "Settings":
        self.local_refresh_seconds = max(15, min(3600, int(self.local_refresh_seconds)))
        self.quota_refresh_seconds = max(60, min(86400, int(self.quota_refresh_seconds)))
        self.timeout_seconds = max(5, min(120, int(self.timeout_seconds)))
        self.opacity = max(0.3, min(1.0, float(self.opacity)))
        self.notify_threshold = max(0, min(100, int(self.notify_threshold)))
        if self.language not in ("system", "en", "tr"):
            self.language = "system"
        if self.theme not in ("system", "light", "dark"):
            self.theme = "system"
        if self.period not in ("today", "5h", "7d", "30d", "all"):
            self.period = "today"
        for d in (self.providers_enabled, self.quota_enabled):
            for p in PROVIDER_IDS:
                d[p] = bool(d.get(p, True))
        return self


def settings_path() -> Path:
    return paths.config_dir() / "settings.json"


def load(path: Path | None = None) -> Settings:
    raw = read_json(path or settings_path(), {})
    if not isinstance(raw, dict):
        raw = {}
    s = Settings()
    known = {f.name: f for f in fields(Settings)}
    for k, v in raw.items():
        if k not in known:
            continue
        default = getattr(s, k)
        if isinstance(default, dict):
            if isinstance(v, dict):
                merged = dict(default)
                merged.update(v)
                setattr(s, k, merged)
        elif isinstance(default, bool):
            if isinstance(v, bool):
                setattr(s, k, v)
        elif isinstance(default, (int, float)) and isinstance(v, (int, float)):
            setattr(s, k, type(default)(v))
        elif isinstance(default, str) and isinstance(v, str):
            setattr(s, k, v)
    return s.clamp()


def save(s: Settings, path: Path | None = None) -> None:
    write_json(path or settings_path(), asdict(s.clamp()))
