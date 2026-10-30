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
    accent: str = "slate"  # slate | ink | amber: accent and app-icon colour
    start_at_login: bool = False
    show_remaining: bool = True  # limits as what is left (else as what is used)
    pinned: dict = field(default_factory=dict)  # provider id -> limit label shown on its ring
    card_order: list = field(default_factory=list)  # provider ids as arranged in the popup
    notify_enabled: bool = True  # master switch for quota notifications
    notify_levels: list = field(default_factory=lambda: [90])  # percent used that warns, once per window each
    notify_limit_reached: bool = True  # a limit is full
    notify_reset: bool = False  # a full limit has reset
    notify_providers: dict = field(default_factory=lambda: {p: True for p in PROVIDER_IDS})
    notify_snooze_until: float = 0.0  # epoch seconds; notifications are held back until then
    update_prices: bool = True  # download the API price list weekly (Tokens page estimate)
    check_updates: bool = True  # ask GitHub for a newer QuotaRing release twice a day
    providers_enabled: dict = field(default_factory=lambda: {p: True for p in PROVIDER_IDS})
    quota_enabled: dict = field(default_factory=lambda: {p: True for p in PROVIDER_IDS})
    claude_command: str = "claude"
    codex_command: str = "codex"

    def clamp(self) -> "Settings":
        self.local_refresh_seconds = max(15, min(3600, int(self.local_refresh_seconds)))
        self.quota_refresh_seconds = max(60, min(86400, int(self.quota_refresh_seconds)))
        self.timeout_seconds = max(5, min(120, int(self.timeout_seconds)))
        levels = self.notify_levels if isinstance(self.notify_levels, list) else []
        self.notify_levels = sorted({int(n) for n in levels
                                     if isinstance(n, (int, float)) and not isinstance(n, bool) and 0 < n <= 100})
        self.notify_snooze_until = max(0.0, float(self.notify_snooze_until))
        if self.language not in ("system", "en", "tr"):
            self.language = "system"
        if self.theme not in ("system", "light", "dark"):
            self.theme = "system"
        if self.accent not in ("slate", "ink", "amber"):
            self.accent = "slate"
        self.pinned = {k: v for k, v in self.pinned.items() if k in PROVIDER_IDS and isinstance(v, str)}
        order = self.card_order if isinstance(self.card_order, list) else []
        self.card_order = [p for i, p in enumerate(order) if p in PROVIDER_IDS and p not in order[:i]]
        for d in (self.providers_enabled, self.quota_enabled, self.notify_providers):
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
        elif isinstance(default, list):
            if isinstance(v, list):
                setattr(s, k, list(v))
        elif isinstance(default, (int, float)) and isinstance(v, (int, float)):
            setattr(s, k, type(default)(v))
        elif isinstance(default, str) and isinstance(v, str):
            setattr(s, k, v)
    # older settings files: a single threshold, 0 meaning off
    old = raw.get("notify_threshold")
    if "notify_levels" not in raw and isinstance(old, int) and not isinstance(old, bool):
        s.notify_enabled = old > 0
        if old > 0:
            s.notify_levels = [old]
    return s.clamp()


def save(s: Settings, path: Path | None = None) -> None:
    write_json(path or settings_path(), asdict(s.clamp()))
