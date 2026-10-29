"""Light and dark palettes (the QML popup and settings window colour themselves from these)."""

from __future__ import annotations

from dataclasses import dataclass

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
                "#9448d6", "#2f8f5b", "#c98a12", "#cf4b3f", "#6b6862")
DARK = Palette("dark", "#18191c", "#222428", "#33363c", "#ecebe8", "#9a9893", "#33363c",
               "#c99cf5", "#5cc28a", "#e0b04a", "#ef6f62", "#9a9893")

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


def resolve(theme: str) -> Palette:
    if theme == "dark":
        return DARK
    if theme == "light":
        return LIGHT
    return DARK if system_is_dark() else LIGHT
