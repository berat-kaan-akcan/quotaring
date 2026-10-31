"""Settings as the QML settings window edits them: flat values, labels, and applying the result."""

from __future__ import annotations

from ..alerts import LEVELS
from ..i18n import language, tr
from ..settings import PROVIDER_IDS, Settings
from ..viewmodel import COLORS

NAMES = {"claude": "Claude Code", "codex": "Codex", "antigravity": "Antigravity"}
NO_QUOTA: dict[str, str] = {}  # providers without any quota source: their toggle is disabled
SCALARS = ("local_refresh_seconds", "quota_refresh_seconds", "timeout_seconds", "theme", "language", "accent",
           "show_remaining", "start_at_login", "notify_enabled", "notify_limit_reached", "notify_reset",
           "update_prices", "check_updates", "claude_command", "codex_command")


def form(s: Settings, autostart_supported: bool, notify_supported: bool = True) -> dict:
    values = {k: getattr(s, k) for k in SCALARS}
    for pid in PROVIDER_IDS:
        values[f"enabled_{pid}"] = s.providers_enabled.get(pid, True)
        values[f"quota_{pid}"] = s.quota_enabled.get(pid, True) and pid not in NO_QUOTA
        values[f"notify_{pid}"] = s.notify_providers.get(pid, True)
    values["notify_levels"] = list(s.notify_levels)
    text = {key: tr(src) for key, src in {
        "general": "General", "appearance": "Appearance", "providers": "Providers", "advanced": "Advanced",
        "track": "Track", "limits": "Limits",
        "local": "Local refresh every", "quota": "Quota refresh every", "timeout": "Query timeout",
        "seconds": "seconds", "theme": "Theme", "system": "Follow system", "light": "Light", "dark": "Dark",
        "language": "Language", "accent": "Accent colour", "slate": "Slate", "ink": "Ink", "amber": "Amber",
        "remaining": "Show limits as the percent left (off: used)", "autostart": "Start at login",
        "prices": "Update API prices", "pricesHint": "Weekly, for the cost estimate on the Tokens page",
        "updates": "Check for updates", "updatesHint": "Shows when a new QuotaRing version is out",
        "notifications": "Notifications", "notifyEnabled": "Quota notifications",
        "notifyEnabledHint": "Each one appears once per limit window",
        "notifyLevels": "Warn when usage reaches",
        "notifyLevelsHint": "Pick one or more, or add your own; only the highest level reached is shown",
        "notifyCustom": "Custom", "notifyCustomHint": "Add your own warning level (1–100 %)",
        "notifyLimit": "When a limit is full", "notifyReset": "When a full limit resets",
        "notifyProviders": "Notify for", "notifyTest": "Send a test notification",
        "notifyNoTray": "Notifications need a system tray", "claudeCommand": "claude command",
        "codexCommand": "codex command",
        "privacy": "Quota checks start the provider's own CLI (no model request). "
                   "The widget never reads or stores credentials.",
    }.items()}
    text["pct"] = "%{n}" if language() == "tr" else "{n}%"
    text["locale"] = language()  # upper-case in the UI language, not the system's (i/İ in Turkish)
    providers = [{"id": pid, "name": NAMES[pid], "color": COLORS[pid], "quotaNote": tr(NO_QUOTA.get(pid, ""))}
                 for pid in PROVIDER_IDS]
    return {"values": values, "text": text, "providers": providers, "autostartSupported": autostart_supported,
            "notifyLevels": list(LEVELS), "notifySupported": notify_supported}


def apply(s: Settings, values: dict) -> None:
    """Copy the window's values into the settings; unknown keys are ignored, ranges are clamped."""
    for k in SCALARS:
        if k not in values:
            continue
        default = getattr(s, k)
        v = values[k]
        if isinstance(default, bool):
            setattr(s, k, bool(v))
        elif isinstance(default, int):
            try:
                setattr(s, k, int(v))
            except (TypeError, ValueError):
                pass
        elif isinstance(v, str):
            setattr(s, k, v.strip())
    for pid in PROVIDER_IDS:
        if f"enabled_{pid}" in values:
            s.providers_enabled[pid] = bool(values[f"enabled_{pid}"])
        if f"quota_{pid}" in values and pid not in NO_QUOTA:
            s.quota_enabled[pid] = bool(values[f"quota_{pid}"])
        if f"notify_{pid}" in values:
            s.notify_providers[pid] = bool(values[f"notify_{pid}"])
    levels = values.get("notify_levels")
    if isinstance(levels, (list, tuple)):
        try:
            s.notify_levels = [int(n) for n in levels]
        except (TypeError, ValueError):
            pass
    s.claude_command = s.claude_command or "claude"
    s.codex_command = s.codex_command or "codex"
    s.clamp()
