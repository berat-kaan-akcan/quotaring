"""Application wiring: engine, background workers, timers, tray, window."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from PySide6.QtCore import QLockFile, QObject, QPointF, QRectF, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import __version__, alerts, autostart, paths, pricing, settings as settings_mod, viewmodel
from .engine import Engine
from .providers import ALL
from .providers.base import shutdown_children
from .i18n import set_language, tr
from .ui import settings_form, theme
from .ui.popup import Backend, Popup, layer_shell_import_dir

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


def make_ring_icon(ring: dict, show_remaining: bool, p: theme.Palette) -> QIcon:
    """Tray icon: a ring around the tightest limit with its number."""
    value = ring["remaining"] if show_remaining else ring["used"]
    tone = QColor({"bad": p.bad, "warn": p.warn}.get(ring["level"], p.accent))
    track = QColor(p.text)
    track.setAlphaF(0.22)
    icon = QIcon()
    for size in (16, 22, 24, 32, 48, 64, 96, 128):
        pm = QPixmap(size, size)
        pm.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)
        lw = max(2.0, size * 0.13)
        rect = QRectF(lw / 2, lw / 2, size - lw, size - lw)
        painter.setPen(QPen(track, lw))
        painter.drawEllipse(rect)
        if value > 0:
            painter.setPen(QPen(tone, lw, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(rect, 90 * 16, -round(360 * 16 * min(1.0, value / 100)))
        font = QFont()
        font.setBold(True)
        font.setPixelSize(max(7, round(size * (0.36 if value >= 100 else 0.5))))
        painter.setFont(font)
        painter.setPen(QColor(p.bad if ring["limited"] else p.text))
        painter.drawText(pm.rect(), Qt.AlignCenter, str(value))
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

        self.palette = theme.resolve(self.settings.theme, self.settings.accent)
        self.icon = make_icon(self.settings.accent)
        app.setWindowIcon(self.icon)
        self.backend = Backend(self.settings, self.palette)
        self.backend.refreshRequested.connect(lambda: self.refresh(force=True))
        self.backend.settingsRequested.connect(self.open_settings)
        self.backend.hideRequested.connect(self.hide_popup)
        self.backend.quitRequested.connect(self.quit)
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
            self.tray.messageClicked.connect(lambda: self.popup.is_visible() or self.popup.show())
            self.tray.show()
        # Without a tray (GNOME without the AppIndicator extension) the popup is a normal window.
        self.popup = Popup(self.backend, docked=self.tray is not None)
        if self.tray is None:
            self.popup.window.closing.connect(lambda *_: self.quit())

        hints = QApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda *_: self.apply_theme())

        self.update_view()
        if not start_hidden or self.tray is None:
            self.popup.show()

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
        self.apply_intervals()
        QTimer.singleShot(0, lambda: self.refresh(force=True))
        QTimer.singleShot(10_000, self.refresh_prices)

    def _build_menu(self) -> QMenu:
        menu = QMenu()
        for text, fn in ((tr("Show / hide"), self.popup_toggle),
                         (tr("Refresh now") + "\tF5", lambda: self.refresh(force=True)),
                         (tr("Settings…") + "\tCtrl+,", self.open_settings)):
            act = QAction(text, menu)
            act.triggered.connect(fn)
            menu.addAction(act)
        menu.addSeparator()
        quit_act = QAction(tr("Quit") + "\tCtrl+Q", menu)
        quit_act.triggered.connect(self.quit)
        menu.addAction(quit_act)
        return menu

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

    def _on_done(self, pid: str, kind: str, result):
        if kind == "prices":
            if result:
                self.update_view()
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
        if self.tray is None:
            return
        for a in self.seen_alerts.take_new(alerts.pending([snap], self.settings.notify_threshold, time.time())):
            # The limit itself as the icon: a ring with what is left, amber or red like the tray.
            left = max(0.0, 100 - a["used"])
            ring = {"available": True, "used": round(a["used"]), "remaining": round(left), "limited": a["limited"],
                    "level": "bad" if a["limited"] or left <= 10 else "warn" if left <= 30 else "ok"}
            icon = make_ring_icon(ring, self.settings.show_remaining, self._panel_palette())
            self.tray.showMessage(a["title"], a["body"], icon, 10000)

    # -- popup / settings -----------------------------------------------
    def apply_theme(self):
        self.palette = theme.resolve(self.settings.theme, self.settings.accent)
        self.backend.set_palette(self.palette)
        self.icon = make_icon(self.settings.accent)
        self.app.setWindowIcon(self.icon)
        self.update_view()

    def open_settings(self):
        self.backend.set_settings_form(settings_form.form(self.settings, autostart.supported()))
        self.popup.open_settings()

    def _data_settings(self) -> tuple:
        """Settings that change what is collected: only these warrant querying the providers again."""
        s = self.settings
        return (dict(s.providers_enabled), dict(s.quota_enabled), s.claude_command, s.codex_command,
                s.timeout_seconds)

    def apply_settings(self, values: dict):
        """Called for every change in the settings window (it has no Save button)."""
        before = (self._data_settings(), self.settings.language, self.settings.update_prices)
        settings_form.apply(self.settings, values)
        if self.settings.update_prices and not before[2]:
            self.refresh_prices()
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
        if self.tray is not None:
            self._menu = self._build_menu()
            self.tray.setContextMenu(self._menu)
        self.backend.set_settings_form(settings_form.form(self.settings, autostart.supported()))
        self.update_view()

    def save_settings(self):
        try:
            settings_mod.save(self.settings)
        except OSError:
            log.warning("could not save settings")

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

