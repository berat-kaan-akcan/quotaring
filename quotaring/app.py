"""Application wiring: engine, background workers, timers, tray, window."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from PySide6.QtCore import QLockFile, QObject, QPoint, QPointF, QRect, QRectF, QRunnable, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import (QAction, QColor, QDesktopServices, QFont, QFontDatabase, QFontMetricsF, QIcon, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import __version__, alerts, autostart, paths, pricing, settings as settings_mod, traypin, updater, viewmodel
from .engine import Engine
from .providers import ALL
from .providers.base import shutdown_children
from .i18n import set_language, tr
from .ui import settings_form, theme
from .ui.popup import Backend, Popup, layer_shell_import_dir, panel_at_top

log = logging.getLogger("quotaring")


def make_icon(accent: str = theme.DEFAULT_ACCENT) -> QIcon:
    """App icon: the QuotaRing mark (a Q drawn as a gauge) on a dark tile; see docs/brand/build_logo.py."""
    color = theme.ACCENTS.get(accent, theme.ACCENTS[theme.DEFAULT_ACCENT])[1]  # the tile is always dark
    icon = QIcon()
    for size in (16, 22, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#18191c"))
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 56 / 256, size * 56 / 256)
        # Mark geometry on a 256 canvas: centre, ring radius, stroke, tail end, scale on the tile.
        # Small sizes use the heavier cut so the ring stays open and the tail visible.
        c, r, w, tail, scale = (124, 74, 50, 106, 0.8) if size <= 32 else (125, 80, 36, 116, 0.74)
        k = size / 256

        def at(v):  # canvas coordinate -> pixel, as translate(124) scale(s) translate(-128) in the SVG
            return (124 + scale * (v - 128)) * k
        rr, ww = r * scale * k, w * scale * k
        p.setPen(QPen(QColor(color), ww, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(at(c) - rr, at(c) - rr, 2 * rr, 2 * rr), 90 * 16, -270 * 16)
        d = 0.70710678
        p.drawLine(QPointF(at(c + r * d), at(c + r * d)), QPointF(at(c + tail * d), at(c + tail * d)))
        p.end()
        icon.addPixmap(pm)
    return icon


def _tray_font() -> QFont:
    """Narrow digits fit taller in the ring: Windows' Bahnschrift Condensed when it is there."""
    if "Bahnschrift SemiBold Condensed" in QFontDatabase.families():
        return QFont("Bahnschrift SemiBold Condensed")
    font = QFont()
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, -0.5)
    return font


# Hand-drawn digits for the tray's small sizes, where font digits blur across pixels.
# "#" is a lit pixel and "|" ends a row.
_DIGITS_5x9 = {
    "0": ".###.|##.##|##.##|##.##|##.##|##.##|##.##|##.##|.###.",
    "1": "..##.|.###.|..##.|..##.|..##.|..##.|..##.|..##.|..##.",
    "2": ".###.|##.##|...##|...##|..##.|.##..|##...|##...|#####",
    "3": ".###.|##.##|...##|...##|..##.|...##|...##|##.##|.###.",
    "4": "...##|..###|.####|##.##|##.##|#####|...##|...##|...##",
    "5": "#####|##...|##...|####.|...##|...##|...##|##.##|.###.",
    "6": ".###.|##...|##...|####.|##.##|##.##|##.##|##.##|.###.",
    "7": "#####|...##|...##|..##.|..##.|.##..|.##..|.##..|.##..",
    "8": ".###.|##.##|##.##|##.##|.###.|##.##|##.##|##.##|.###.",
    "9": ".###.|##.##|##.##|##.##|.####|...##|...##|...##|.###.",
}
_DIGITS_6x11 = {
    "0": ".####.|##..##|##..##|##..##|##..##|##..##|##..##|##..##|##..##|##..##|.####.",
    "1": "..##..|.###..|..##..|..##..|..##..|..##..|..##..|..##..|..##..|..##..|..##..",
    "2": ".####.|##..##|....##|....##|...##.|..##..|.##...|##....|##....|##....|######",
    "3": ".####.|##..##|....##|....##|....##|..###.|....##|....##|....##|##..##|.####.",
    "4": "....##|...###|..####|.##.##|##..##|##..##|######|....##|....##|....##|....##",
    "5": "######|##....|##....|##....|#####.|....##|....##|....##|....##|##..##|.####.",
    "6": ".####.|##....|##....|##....|#####.|##..##|##..##|##..##|##..##|##..##|.####.",
    "7": "######|....##|....##|....##|...##.|...##.|..##..|..##..|..##..|..##..|..##..",
    "8": ".####.|##..##|##..##|##..##|##..##|.####.|##..##|##..##|##..##|##..##|.####.",
    "9": ".####.|##..##|##..##|##..##|##..##|.#####|....##|....##|....##|....##|.####.",
}
_DIGITS_3x7 = {
    "0": "###|#.#|#.#|#.#|#.#|#.#|###",
    "1": ".#|##|.#|.#|.#|.#|.#",
    "2": "###|..#|..#|###|#..|#..|###",
    "3": "###|..#|..#|###|..#|..#|###",
    "4": "#.#|#.#|#.#|###|..#|..#|..#",
    "5": "###|#..|#..|###|..#|..#|###",
    "6": "###|#..|#..|###|#.#|#.#|###",
    "7": "###|..#|..#|.#.|.#.|.#.|.#.",
    "8": "###|#.#|#.#|###|#.#|#.#|###",
    "9": "###|#.#|#.#|###|..#|..#|###",
}
_DIGITS_100 = {**_DIGITS_5x9, "1": ".##|###|.##|.##|.##|.##|.##|.##|.##"}
# Icon size -> ((glyphs, scale) for up to two digits, (glyphs, scale) for three). Larger sizes draw
# the font. The digits are as large as the ring leaves room for, about a pixel inside it.
_PIXEL_DIGITS = {
    16: ((_DIGITS_5x9, 1), (_DIGITS_3x7, 1)),
    20: ((_DIGITS_6x11, 1), (_DIGITS_3x7, 1)),
    22: ((_DIGITS_6x11, 1), (_DIGITS_3x7, 1)),
    24: ((_DIGITS_6x11, 1), (_DIGITS_100, 1)),
    30: ((_DIGITS_5x9, 2), (_DIGITS_3x7, 2)),
    32: ((_DIGITS_5x9, 2), (_DIGITS_3x7, 2)),
    40: ((_DIGITS_6x11, 2), (_DIGITS_3x7, 2)),
}


def _pixel_digits(text: str, size: int) -> tuple[list[list[str]], int] | None:
    """The text's hand-drawn glyph rows and their scale at this icon size, or None to draw the font."""
    if size not in _PIXEL_DIGITS or len(text) > 3:
        return None
    table, scale = _PIXEL_DIGITS[size][len(text) > 2]
    if any(c not in table for c in text):
        return None
    return [table[c].split("|") for c in text], scale


def make_ring_icon(ring: dict, show_remaining: bool, p: theme.Palette) -> QIcon:
    """Tray icon: a ring around the tightest limit with its number."""
    value = ring["remaining"] if show_remaining else ring["used"]
    tone = QColor({"bad": p.bad, "warn": p.warn}.get(ring["level"], p.accent))
    track = QColor(p.text)
    track.setAlphaF(0.22)
    icon = QIcon()
    # 20, 30 and 40: Windows' tray at 125, 150 (24 px is 1.5x16 too) and 200 % scaling.
    for size in (16, 20, 22, 24, 30, 32, 40, 48, 64, 96, 128):
        pm = QPixmap(size, size)
        pm.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)
        lw = max(2.0, size * 0.11)  # thick enough to read as a ring beside the number
        rect = QRectF(lw / 2, lw / 2, size - lw, size - lw)
        painter.setPen(QPen(track, lw))
        painter.drawEllipse(rect)
        if value > 0:
            painter.setPen(QPen(tone, lw, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(rect, 90 * 16, -round(360 * 16 * min(1.0, value / 100)))
        text, inner = str(value), size - 2 * lw
        color = QColor(p.bad if ring["limited"] else p.text)
        pixel = _pixel_digits(text, size)
        if pixel:
            # Whole pixels, centred: crisp where a font would smear at this size.
            glyphs, k = pixel
            w = (sum(len(g[0]) for g in glyphs) + len(glyphs) - 1) * k
            x, y = (size - w) // 2, (size - len(glyphs[0]) * k + 1) // 2
            lit = []
            for g in glyphs:
                for r, row in enumerate(g):
                    for c, ch in enumerate(row):
                        if ch == "#":
                            lit.append(QRect(x + c * k, y + r * k, k, k))
                x += (len(g[0]) + 1) * k
            # The digits fill the ring, so their corners reach it: a gap is cut around them.
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            for px_rect in lit:
                painter.fillRect(px_rect.adjusted(-1, -1, 1, 1), Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            for px_rect in lit:
                painter.fillRect(px_rect, color)
            painter.end()
            icon.addPixmap(pm)
            continue
        # The number as large as the inside of the ring allows: tray icons are tiny.
        font = _tray_font()
        px = round(inner * 1.3)
        while True:
            font.setPixelSize(px)
            ink = QFontMetricsF(font).tightBoundingRect(text)
            if px <= 6 or (ink.width() <= inner * 0.92 and ink.height() <= inner * 0.78):
                break
            px -= 1
        # Centred on the digits' ink, not the font's line box, so they sit in the ring's middle.
        path = QPainterPath()
        path.addText(QPointF((size - ink.width()) / 2 - ink.x(), (size - ink.height()) / 2 - ink.y()), font, text)
        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.strokePath(path, QPen(Qt.transparent, size / 24, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.fillPath(path, color)
        painter.end()
        icon.addPixmap(pm)
    return icon


class _Signals(QObject):
    done = Signal(str, str, object)  # provider id, kind ("local"|"quota"), result


class Job(QRunnable):
    def __init__(self, fn, pid: str, kind: str, signals: _Signals):
        super().__init__()
        self.fn, self.pid, self.kind, self.signals = fn, pid, kind, signals

    def run(self):
        try:
            result = self.fn(self.pid)
        except Exception as e:  # noqa: BLE001 - engine/provider already isolate; belt and braces
            log.warning("worker failed: %s %s (%s)", self.pid, self.kind, type(e).__name__)
            result = None
        self.signals.done.emit(self.pid, self.kind, result)


class Controller(QObject):
    def __init__(self, app: QApplication, start_hidden: bool):
        super().__init__()
        self.app = app
        self.settings = settings_mod.load()
        set_language(self.settings.language)  # before any widget is built
        self.providers = [P(self.settings) for P in ALL]
        self.engine = Engine(self.settings, self.providers)
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(4)
        self.signals = _Signals()
        self.signals.done.connect(self._on_done)
        self.seen_alerts = alerts.Seen()
        self.release = None  # a newer release, once one is found
        self.update_state = "idle"  # idle | installing | failed
        self.install_kind = updater.install_kind()

        self.palette = theme.resolve(self.settings.theme, self.settings.accent)
        self.icon = make_icon(self.settings.accent)
        app.setWindowIcon(self.icon)
        self.backend = Backend(self.settings, self.palette)
        self.backend.refreshRequested.connect(lambda: self.refresh(force=True))
        self.backend.settingsRequested.connect(self.open_settings)
        self.backend.hideRequested.connect(self.hide_popup)
        self.backend.quitRequested.connect(self.quit)
        self.backend.testNotificationRequested.connect(self.test_notification)
        self.backend.updateRequested.connect(self.install_update)
        self.backend.prefsSaved.connect(self.save_settings)
        self.backend.settingsSaved.connect(self.apply_settings)
        self.backend.prefsChanged.connect(self.update_view)  # the tray ring follows used/left

        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.icon)
            self._menu = self._build_menu()
            self.tray.setContextMenu(self._menu)
            self.tray.setToolTip(tr("QuotaRing"))
            self.tray.activated.connect(self._tray_activated)
            self.tray.messageClicked.connect(lambda: self.popup.is_visible() or self.popup.show(self.tray_point()))
            self.tray.show()
            if sys.platform == "win32" and getattr(sys, "frozen", False):
                # Explorer adds the icon's settings entry a moment after it first appears.
                for delay in (0, 3000, 15000):
                    QTimer.singleShot(delay, lambda: traypin.promote(sys.executable))
        # Without a tray (GNOME without the AppIndicator extension) the popup is a normal window.
        self.popup = Popup(self.backend, docked=self.tray is not None)
        if self.tray is None:
            self.popup.window.closing.connect(lambda *_: self.quit())

        hints = QApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda *_: self.apply_theme())

        self.update_view()
        if not start_hidden or self.tray is None:
            self.popup.show(self.tray_point())
        # The installer of the last update is no longer needed. Not at once: on Windows the setup
        # that started this copy may still be running from that folder.
        QTimer.singleShot(60_000, lambda: self.update_state == "installing" or updater.clean_downloads())

        self.local_timer = QTimer(self)
        self.local_timer.timeout.connect(lambda: self.refresh(local=True, quota=False))
        self.quota_timer = QTimer(self)
        self.quota_timer.timeout.connect(lambda: self.refresh(local=False, quota=True))
        self.tick = QTimer(self)  # keeps countdowns and "updated … ago" current
        self.tick.timeout.connect(self.update_view)
        self.tick.start(30_000)
        self.prices_timer = QTimer(self)  # the list itself is fetched at most weekly
        self.prices_timer.timeout.connect(self.refresh_prices)
        self.prices_timer.start(6 * 3600 * 1000)
        self.update_timer = QTimer(self)  # GitHub itself is asked at most twice a day
        self.update_timer.timeout.connect(self.check_updates)
        self.update_timer.start(3600 * 1000)
        self.apply_intervals()
        QTimer.singleShot(0, lambda: self.refresh(force=True))
        QTimer.singleShot(10_000, self.refresh_prices)
        QTimer.singleShot(20_000, self.check_updates)

    def _build_menu(self) -> QMenu:
        menu = QMenu()
        for text, fn in ((tr("Show / hide"), self.popup_toggle),
                         (tr("Refresh now") + "\tF5", lambda: self.refresh(force=True)),
                         (tr("Settings…") + "\tCtrl+,", self.open_settings)):
            act = QAction(text, menu)
            act.triggered.connect(fn)
            menu.addAction(act)
        menu.addMenu(self._notify_menu(menu))
        if self.release is not None and self.settings.check_updates:
            act = QAction(tr("Update to {v}").format(v=self.release.version), menu)
            act.setEnabled(self.update_state != "installing")
            act.triggered.connect(self.install_update)
            menu.addAction(act)
        menu.addSeparator()
        quit_act = QAction(tr("Quit") + "\tCtrl+Q", menu)
        quit_act.triggered.connect(self.quit)
        menu.addAction(quit_act)
        return menu

    def _notify_menu(self, parent: QMenu) -> QMenu:
        """On / off and a temporary mute, without opening the settings."""
        sub = QMenu(tr("Notifications"), parent)
        sub.aboutToShow.connect(lambda: self._fill_notify_menu(sub))
        self._fill_notify_menu(sub)
        return sub

    def _fill_notify_menu(self, sub: QMenu):
        sub.clear()
        s = self.settings
        on = QAction(tr("Notifications on"), sub)
        on.setCheckable(True)
        on.setChecked(s.notify_enabled)
        on.toggled.connect(lambda v: self._set_notify(notify_enabled=v))
        sub.addAction(on)
        sub.addSeparator()
        now = time.time()
        if s.notify_snooze_until > now:
            info = QAction(tr("Muted until {t}").format(t=time.strftime("%H:%M", time.localtime(s.notify_snooze_until))), sub)
            info.setEnabled(False)
            sub.addAction(info)
            resume = QAction(tr("Resume notifications"), sub)
            resume.triggered.connect(lambda: self._set_notify(notify_snooze_until=0.0))
            sub.addAction(resume)
        else:
            y, m, d = time.localtime(now)[:3]
            tomorrow = time.mktime((y, m, d + 1, 0, 0, 0, 0, 0, -1))  # local midnight; mktime normalises the day
            for text, until in ((tr("Mute for 1 hour"), now + 3600), (tr("Mute until tomorrow"), tomorrow)):
                act = QAction(text, sub)
                act.setEnabled(s.notify_enabled)
                act.triggered.connect(lambda _=False, u=until: self._set_notify(notify_snooze_until=u))
                sub.addAction(act)

    def _set_notify(self, **changes):
        for k, v in changes.items():
            setattr(self.settings, k, v)
        self.save_settings()
        self.backend.set_settings_form(settings_form.form(self.settings, autostart.supported(), self.tray is not None))

    # -- refresh --------------------------------------------------------
    def apply_intervals(self):
        self.local_timer.start(self.settings.local_refresh_seconds * 1000)
        self.quota_timer.start(60_000)  # cheap check; engine decides when quota is due

    def refresh(self, local: bool = True, quota: bool = True, force: bool = False):
        now = time.time()
        for p in self.providers:
            if local and self.engine.try_begin(p.id, "local"):
                self.pool.start(Job(self.engine.run_local, p.id, "local", self.signals))
            if quota and self.engine.quota_due(p.id, now, force) and self.engine.try_begin(p.id, "quota"):
                self.pool.start(Job(self.engine.run_quota, p.id, "quota", self.signals))
        self._update_status()

    def refresh_prices(self):
        if self.settings.update_prices:
            self.pool.start(Job(lambda _pid: pricing.refresh(), "prices", "prices", self.signals))

    def check_updates(self):
        if self.settings.check_updates and self.update_state != "installing":
            self.pool.start(Job(lambda _pid: updater.check(__version__), "update", "update-check", self.signals))

    def _show_update(self):
        """The popup's banner and the tray's menu item for a newer release."""
        r = self.release
        if r is None or not self.settings.check_updates:
            self.backend.set_update({})
        else:
            auto = updater.can_install(r, self.install_kind)
            text = {"idle": tr("QuotaRing {v} is available"), "installing": tr("Updating to {v}…"),
                    "failed": tr("Could not update to {v}")}[self.update_state].format(v=r.version)
            action = "" if self.update_state == "installing" else                 tr("Update") if auto and self.update_state == "idle" else tr("Download page")
            self.backend.set_update({"text": text, "action": action, "busy": self.update_state == "installing"})
        if self.tray is not None:
            self._menu = self._build_menu()
            self.tray.setContextMenu(self._menu)

    def install_update(self):
        """Install the newer release and restart; where this copy cannot do that, open its page."""
        r = self.release
        if r is None or self.update_state == "installing":
            return
        if self.update_state == "failed" or not updater.can_install(r, self.install_kind):
            QDesktopServices.openUrl(QUrl(r.page))
            return
        self.update_state = "installing"
        self._show_update()

        def run(_pid):
            try:
                updater.install(r, self.install_kind)
                return True
            except updater.UpdateError as e:
                log.warning("update failed: %s", e)
                return False
        self.pool.start(Job(run, "update", "update-install", self.signals))

    def _on_done(self, pid: str, kind: str, result):
        if kind == "prices":
            if result:
                self.update_view()
            return
        if kind == "update-check":
            if self.update_state != "installing":
                self.release = result
                self._show_update()
            return
        if kind == "update-install":
            if result:
                self.quit()  # the new version starts once this one has gone
            else:
                self.update_state = "failed"
                self._show_update()
            return
        self.engine.end(pid, kind)
        if result is not None:
            snap = (self.engine.apply_local if kind == "local" else self.engine.apply_quota)(pid, result)
            self._maybe_notify(snap)  # local scans can reveal a limit hit before the next quota poll
        if not self.engine.busy:
            self.engine.save_cache()
            self.update_view()
        self._update_status()

    def _update_status(self):
        self.backend.set_busy(bool(self.engine.busy))

    def update_view(self):
        now = time.time()
        view = viewmodel.widget_view(self.engine.snapshots.values(), now)
        self.backend.set_view(view)
        if self.tray is not None:
            tip = viewmodel.limits_tooltip(view["limits"], self.settings.show_remaining) or view["tooltip"]
            self.tray.setToolTip(tr("QuotaRing") + "\n" + tip)
            ring = view["ring"]
            self.tray.setIcon(make_ring_icon(ring, self.settings.show_remaining, self._panel_palette())
                              if ring["available"] else self.icon)

    def _panel_palette(self):
        return theme.with_accent(theme.DARK if theme.system_is_dark() else theme.LIGHT, self.settings.accent)

    def _maybe_notify(self, snap):
        s = self.settings
        if self.tray is None or not s.notify_enabled or not s.notify_providers.get(snap.provider_id, True):
            return
        now = time.time()
        found = alerts.pending([snap], s.notify_levels, now, limit_reached=s.notify_limit_reached,
                               reset=s.notify_reset)
        # Muted: still recorded as shown, so they do not all arrive at once when the mute ends.
        new = self.seen_alerts.take_new(found, now)
        if s.notify_snooze_until > now:
            return
        for a in new:
            self._show_alert(a)

    def _show_alert(self, a: dict):
        # The limit itself as the icon: a ring with what is left, amber or red like the tray.
        left = max(0.0, 100 - a["used"])
        ring = {"available": True, "used": round(a["used"]), "remaining": round(left), "limited": a["limited"],
                "level": "bad" if a["limited"] or left <= 10 else "warn" if left <= 30 else "ok"}
        icon = make_ring_icon(ring, self.settings.show_remaining, self._panel_palette())
        self.tray.showMessage(a["title"], a["body"], icon, 10000)

    def test_notification(self):
        if self.tray is not None:
            self._show_alert({"title": tr("Test notification"), "body": tr("Notifications will look like this."),
                              "used": 75.0, "limited": False})

    # -- popup / settings -----------------------------------------------
    def apply_theme(self):
        self.palette = theme.resolve(self.settings.theme, self.settings.accent)
        self.backend.set_palette(self.palette)
        self.icon = make_icon(self.settings.accent)
        self.app.setWindowIcon(self.icon)
        self.update_view()

    def open_settings(self):
        self.backend.set_settings_form(settings_form.form(self.settings, autostart.supported(), self.tray is not None))
        self.popup.open_settings()

    def _data_settings(self) -> tuple:
        """Settings that change what is collected: only these warrant querying the providers again."""
        s = self.settings
        return (dict(s.providers_enabled), dict(s.quota_enabled), s.claude_command, s.codex_command,
                s.timeout_seconds)

    def apply_settings(self, values: dict):
        """Called for every change in the settings window (it has no Save button)."""
        before = (self._data_settings(), self.settings.language, self.settings.update_prices,
                  self.settings.check_updates)
        settings_form.apply(self.settings, values)
        if self.settings.update_prices and not before[2]:
            self.refresh_prices()
        if self.settings.check_updates != before[3]:
            self._show_update()  # hides the banner when turned off
            self.check_updates()
        if self.settings.language != before[1]:
            self.apply_language()
        try:
            if autostart.supported() and autostart.is_enabled() != self.settings.start_at_login:
                autostart.set_enabled(self.settings.start_at_login)
        except OSError:
            log.warning("could not change start-at-login")
        self.save_settings()
        self.backend.notify_settings_changed()
        self.apply_theme()
        self.apply_intervals()
        if self._data_settings() != before[0]:
            self.engine.next_quota_at.clear()
            self.refresh(force=True)

    def apply_language(self):
        """Switch the UI language now: every text is translated when the view is rebuilt."""
        set_language(self.settings.language)
        self._show_update()  # also rebuilds the tray menu
        self.backend.set_settings_form(settings_form.form(self.settings, autostart.supported(), self.tray is not None))
        self.update_view()

    def save_settings(self):
        try:
            settings_mod.save(self.settings)
        except OSError:
            log.warning("could not save settings")

    def tray_point(self) -> QPoint | None:
        """The tray icon's centre, else the corner by the clock (the icon in the hidden-icons flyout
        or a tray that does not tell); None without a tray, where the popup is a normal window."""
        if self.tray is None:
            return None
        g = self.tray.geometry()
        if g.isValid() and not g.isEmpty():
            return g.center()
        screen = QApplication.primaryScreen()
        if screen is None:
            return None
        a = screen.availableGeometry()
        return QPoint(a.right(), a.top() if panel_at_top(screen) else a.bottom())

    def popup_toggle(self):
        self.popup.toggle()

    def hide_popup(self):
        if self.tray is not None:
            self.popup.hide()

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.popup.toggle()

    def quit(self):
        self.save_settings()
        self.engine.save_cache()
        self.pool.clear()  # drop queued jobs
        shutdown_children()  # running quota queries end now instead of after their timeout
        self.pool.waitForDone(5000)
        if self.tray:
            self.tray.hide()
        self.app.quit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quotaring", description="AI usage desktop widget")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--hidden", action="store_true", help="start hidden in the tray")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    parser.add_argument("--allow-multiple", action="store_true", help="skip the single-instance check")
    parser.add_argument("--xwayland", action="store_true",
                        help="on Wayland, run through XWayland instead of anchoring the popup with layer-shell")
    parser.add_argument("--print", dest="print_json", action="store_true",
                        help="collect once and print the snapshot as JSON (no window)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.print_json:
        return print_once()

    if os.environ.get("WAYLAND_DISPLAY") and os.environ.get("DISPLAY") and (
            args.xwayland or layer_shell_import_dir() is None):
        # Wayland clients cannot place their own windows; without layer-shell, XWayland can.
        os.environ["QT_QPA_PLATFORM"] = "xcb"
    # One widget per user session. QLockFile checks the owner PID, so a crashed run's lock is taken over.
    lock_dir = paths.cache_dir()
    lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = QLockFile(str(lock_dir / "instance.lock"))
    lock.setStaleLockTime(5000)
    if not args.allow_multiple and not lock.tryLock(100):
        print("QuotaRing is already running (use the tray icon, or pass --allow-multiple).",
              file=sys.stderr)
        return 1
    app = QApplication(sys.argv[:1])
    app.setApplicationName("QuotaRing")
    app.setDesktopFileName("quotaring")
    app.setQuitOnLastWindowClosed(False)
    _controller = Controller(app, start_hidden=args.hidden)  # noqa: F841 - keep alive
    code = app.exec()
    lock.unlock()
    return code


def print_once() -> int:
    import json
    from concurrent.futures import ThreadPoolExecutor

    s = settings_mod.load()
    eng = Engine(s, [P(s) for P in ALL])
    with ThreadPoolExecutor(6) as ex:
        futs = {(pid, k): ex.submit(eng.run_local if k == "local" else eng.run_quota, pid)
                for pid in eng.providers for k in ("local", "quota")}
    for (pid, k), f in futs.items():
        (eng.apply_local if k == "local" else eng.apply_quota)(pid, f.result())
    eng.save_cache()
    out = {pid: s.to_dict() for pid, s in eng.snapshots.items()}
    for snap in out.values():  # keep the output short: drop per-model details of long periods
        for per in snap["local"]["periods"]:
            per.pop("by_model", None) if per["key"] in ("30d", "all") else None
    print(json.dumps({"cache_dir": str(paths.cache_dir()), "providers": out}, indent=1))
    return 0

