"""Light and dark palettes and the stylesheet built from them."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication


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
                "#3d6fd9", "#2f8f5b", "#c98a12", "#cf4b3f", "#6b6862")
DARK = Palette("dark", "#18191c", "#222428", "#33363c", "#ecebe8", "#9a9893", "#33363c",
               "#7aa2f7", "#5cc28a", "#e0b04a", "#ef6f62", "#9a9893")

PROVIDER_COLORS = {"claude": "#d97757", "codex": "#10a37f", "antigravity": "#4285f4"}


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


def with_alpha(color: str, alpha: float) -> str:
    c = QColor(color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{max(0, min(255, int(alpha * 255)))})"


def stylesheet(p: Palette) -> str:
    return f"""
    QWidget {{ color: {p.text}; font-size: 10pt; }}
    QLabel#title {{ font-weight: 600; font-size: 10.5pt; }}
    QLabel#muted, QLabel#small {{ color: {p.muted}; }}
    QLabel#small {{ font-size: 8.5pt; }}
    QLabel#section {{ color: {p.muted}; font-size: 8pt; font-weight: 600; letter-spacing: 0.5px; }}
    QLabel#big {{ font-size: 12pt; font-weight: 600; }}
    QFrame#card {{ background: {p.card}; border: 1px solid {p.border}; border-radius: 10px; }}
    QToolButton {{ border: none; border-radius: 6px; padding: 3px 5px; color: {p.muted}; }}
    QToolButton:hover {{ background: {p.track}; color: {p.text}; }}
    QComboBox {{ background: {p.card}; border: 1px solid {p.border}; border-radius: 6px; padding: 2px 6px; }}
    QComboBox QAbstractItemView {{ background: {p.card}; color: {p.text}; selection-background-color: {p.track}; }}
    QTableWidget {{ background: transparent; border: none; gridline-color: transparent; }}
    QTableWidget::item {{ padding: 0 2px; }}
    QHeaderView {{ background: transparent; border: none; }}
    QHeaderView::section {{ background: transparent; color: {p.muted}; border: none;
        border-bottom: 1px solid {p.border}; font-size: 8pt; padding: 2px; }}
    QTableCornerButton::section {{ background: transparent; border: none; }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 3px; min-height: 24px; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
        background: none; height: 0; }}
    QDialog, QGroupBox {{ background: {p.bg}; }}
    QSpinBox, QLineEdit {{ background: {p.card}; border: 1px solid {p.border}; border-radius: 5px; padding: 2px 4px; }}
    QToolTip {{ background: {p.card}; color: {p.text}; border: 1px solid {p.border}; }}
    """
