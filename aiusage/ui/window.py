"""The compact, frameless widget window."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QScrollArea, QSizeGrip, QToolButton,
                               QVBoxLayout, QWidget)

from ..i18n import tr
from .card import ProviderCard
from .theme import Palette, stylesheet

PERIODS = [("today", "Today"), ("5h", "Last 5 hours"), ("7d", "Last 7 days"),
           ("30d", "Last 30 days"), ("all", "All scanned")]


class Header(QWidget):
    """Drag handle. On Wayland only the compositor can move windows: use startSystemMove."""

    def __init__(self, window: QWidget):
        super().__init__()
        self._win = window
        self._drag: QPoint | None = None

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        handle = self._win.windowHandle()
        if handle is not None and handle.startSystemMove():
            return
        self._drag = e.globalPosition().toPoint() - self._win.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self._win.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _e):
        self._drag = None


class MainWindow(QWidget):
    refresh_requested = Signal()
    settings_requested = Signal()
    hide_requested = Signal()
    mode_changed = Signal(bool, str)  # expanded, period

    def __init__(self, provider_meta: list[tuple[str, str]], palette: Palette, settings):
        super().__init__()
        self.settings = settings
        self.palette_ = palette
        self.setWindowTitle(tr("AI Usage"))
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.apply_flags()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(8)

        self.header = Header(self)
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(2, 0, 0, 0)
        hl.setSpacing(2)
        title = QLabel(tr("AI Usage"))
        title.setObjectName("title")
        hl.addWidget(title)
        self.status = QLabel("")
        self.status.setObjectName("small")
        hl.addWidget(self.status)
        hl.addStretch(1)
        self.btn_refresh = self._button("⟳", tr("Refresh now"))
        self.btn_expand = self._button("▾", tr("Expand / collapse details"))
        self.btn_settings = self._button("⚙", tr("Settings"))
        self.btn_hide = self._button("✕", tr("Hide to tray"))
        for b in (self.btn_refresh, self.btn_expand, self.btn_settings, self.btn_hide):
            hl.addWidget(b)
        outer.addWidget(self.header)

        self.period_box = QComboBox()
        for key, label in PERIODS:
            self.period_box.addItem(tr(label), key)
        self.period_box.setToolTip(tr("Period for the per-model breakdown"))
        prow = QHBoxLayout()
        lab = QLabel(tr("Breakdown:"))
        lab.setObjectName("small")
        prow.addWidget(lab)
        prow.addWidget(self.period_box)
        prow.addStretch(1)
        self.period_row = QWidget()
        self.period_row.setLayout(prow)
        prow.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.period_row)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        self.cards: dict[str, ProviderCard] = {}
        for pid, name in provider_meta:
            card = ProviderCard(pid, name, palette)
            self.cards[pid] = card
            bl.addWidget(card)
        bl.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidget(body)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body.setAutoFillBackground(False)
        self.scroll.viewport().setAutoFillBackground(False)
        outer.addWidget(self.scroll, 1)

        grip_row = QHBoxLayout()
        grip_row.addStretch(1)
        grip_row.addWidget(QSizeGrip(self))
        grip_row.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(grip_row)

        self.btn_refresh.clicked.connect(self.refresh_requested)
        self.btn_settings.clicked.connect(self.settings_requested)
        self.btn_hide.clicked.connect(self.hide_requested)
        self.btn_expand.clicked.connect(self._toggle_expand)
        self.period_box.currentIndexChanged.connect(self._period_changed)

        idx = max(0, self.period_box.findData(settings.period))
        self.period_box.setCurrentIndex(idx)
        self.set_palette(palette)
        self._apply_mode()
        self.setMinimumSize(300, 220)

    def _button(self, text: str, tip: str) -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setAccessibleName(tip)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def apply_flags(self):
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self.settings.always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        visible = self.isVisible()
        self.setWindowFlags(flags)
        if visible:
            self.show()

    def set_palette(self, palette: Palette):
        self.palette_ = palette
        self.setStyleSheet(stylesheet(palette))
        for c in self.cards.values():
            c.palette_ = palette
            c.pill.palette_ = palette
            if c.snapshot:
                c.update_snapshot(c.snapshot)
        self.update()

    def _toggle_expand(self):
        self.settings.expanded = not self.settings.expanded
        self._apply_mode()
        self.mode_changed.emit(self.settings.expanded, self.settings.period)

    def _period_changed(self, _i):
        self.settings.period = self.period_box.currentData()
        self._apply_mode()
        self.mode_changed.emit(self.settings.expanded, self.settings.period)

    def _apply_mode(self):
        exp = self.settings.expanded
        self.btn_expand.setText("▴" if exp else "▾")
        self.period_row.setVisible(exp)
        for c in self.cards.values():
            c.set_mode(exp, self.settings.period)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(0, 0, -1, -1), 14, 14)
        bg = QColor(self.palette_.bg)
        bg.setAlphaF(self.settings.opacity)
        p.fillPath(path, bg)
        p.setPen(QColor(self.palette_.border))
        p.drawPath(path)
