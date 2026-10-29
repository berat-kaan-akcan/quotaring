"""Light and dark palettes (the QML popup and settings window colour themselves from these)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    card: str
    border: str
    text: str
    muted: str
    track: str
    accent: str
    ok: str
    warn: str
    bad: str
    info: str


LIGHT = Palette("light", "#f6f5f2", "#ffffff", "#e3e0da", "#1d1c1a", "#6b6862", "#ebe8e2",
                "#3f5468", "#2f8f5b", "#c98a12", "#cf4b3f", "#6b6862")
DARK = Palette("dark", "#18191c", "#222428", "#33363c", "#ecebe8", "#9a9893", "#33363c",
               "#a9b8c8", "#5cc28a", "#e0b04a", "#ef6f62", "#9a9893")

# Accent colours (the logo's colour too; Settings > Accent colour): light theme, dark theme.
ACCENTS = {
    "slate": ("#3f5468", "#a9b8c8"),
    "ink": ("#1d1c1a", "#ecebe8"),
    "amber": ("#a15f00", "#f2b544"),
}
DEFAULT_ACCENT = "slate"
# Amber would match the "limit near" colour, so the warning moves to orange with it.
WARN_WITH_AMBER = ("#c2581a", "#f0874a")


def with_accent(p: Palette, accent: str) -> Palette:
    light, dark = ACCENTS.get(accent, ACCENTS[DEFAULT_ACCENT])
    is_dark = p.name == "dark"
    p = replace(p, accent=dark if is_dark else light)
    if accent == "amber":
        p = replace(p, warn=WARN_WITH_AMBER[1] if is_dark else WARN_WITH_AMBER[0])
    return p


def system_is_dark() -> bool:
    hints = QGuiApplication.styleHints()
    scheme = getattr(hints, "colorScheme", None)
    if scheme is not None:
        s = scheme()
        if s == Qt.ColorScheme.Dark:
            return True
        if s == Qt.ColorScheme.Light:
            return False
    return QGuiApplication.palette().window().color().lightness() < 128


def resolve(theme: str, accent: str = DEFAULT_ACCENT) -> Palette:
    if theme == "dark":
        base = DARK
    elif theme == "light":
        base = LIGHT
    else:
        base = DARK if system_is_dark() else LIGHT
    return with_accent(base, accent)
