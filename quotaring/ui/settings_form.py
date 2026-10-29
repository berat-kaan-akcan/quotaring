"""Settings as the QML settings window edits them: flat values, labels, and applying the result."""

from __future__ import annotations

from ..i18n import language, tr
from ..settings import PROVIDER_IDS, Settings
from ..viewmodel import COLORS

NAMES = {"claude": "Claude Code", "codex": "Codex", "antigravity": "Antigravity"}
NO_QUOTA: dict[str, str] = {}  # providers without any quota source: their toggle is disabled
SCALARS = ("local_refresh_seconds", "quota_refresh_seconds", "timeout_seconds", "theme", "language", "accent",
           "show_remaining", "start_at_login", "notify_threshold", "update_prices", "claude_command", "codex_command")


def form(s: Settings, autostart_supported: bool) -> dict:
    values = {k: getattr(s, k) for k in SCALARS}
    for pid in PROVIDER_IDS:
        values[f"enabled_{pid}"] = s.providers_enabled.get(pid, True)
        values[f"quota_{pid}"] = s.quota_enabled.get(pid, True) and pid not in NO_QUOTA
    text = {key: tr(src) for key, src in {
        "title": "QuotaRing — Settings", "general": "General", "appearance": "Appearance",
        "notifications": "Notifications", "providers": "Providers", "commands": "Command paths",
        "local": "Local refresh every", "quota": "Quota refresh every", "timeout": "Query timeout",
        "seconds": "seconds", "theme": "Theme", "system": "Follow system", "light": "Light", "dark": "Dark",
        "language": "Language", "accent": "Accent colour", "slate": "Slate", "ink": "Ink", "amber": "Amber",
        "remaining": "Show limits as the percent left (off: used)", "autostart": "Start at login",
        "autostartHint": "Start QuotaRing when you log in", "prices": "Update API prices",
        "pricesHint": "Weekly, from the LiteLLM and OpenRouter price lists; for the cost estimate on the Tokens page",
        "notify": "Notify at quota",
        "notifyHint": "Notify when a limit's use reaches", "off": "Off", "track": "Track this provider",
        "checkQuota": "Check the provider's account limits", "claudeCommand": "claude command",
        "codexCommand": "codex command", "close": "Close", "instant": "Changes apply right away",
        "privacy": "Quota checks start the provider's own CLI (no model request). "
                   "The widget never reads or stores credentials.",
    }.items()}
    text["pct"] = "%{n}" if language() == "tr" else "{n}%"
    text["locale"] = language()  # upper-case in the UI language, not the system's (i/İ in Turkish)
    providers = [{"id": pid, "name": NAMES[pid], "color": COLORS[pid], "quotaNote": tr(NO_QUOTA.get(pid, ""))}
                 for pid in PROVIDER_IDS]
    return {"values": values, "text": text, "providers": providers, "autostartSupported": autostart_supported}


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
    s.claude_command = s.claude_command or "claude"
    s.codex_command = s.codex_command or "codex"
    s.clamp()
