"""Application wiring: engine, background workers, timers, tray, window."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from PySide6.QtCore import QLockFile, QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import __version__, alerts, autostart, paths, settings as settings_mod
from .engine import Engine
from .providers import ALL
from .providers.base import shutdown_children
from .i18n import set_language, tr
from .ui import format as fmt, theme
from .ui.settings_dialog import SettingsDialog
from .ui.window import MainWindow

log = logging.getLogger("aiusage")


def make_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 22, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor(0, 0, 0, 0))
        p.setBrush(QColor("#25272c"))
        p.drawRoundedRect(0, 0, size, size, size * 0.22, size * 0.22)
        w = size / 7
        for i, (h, c) in enumerate(((0.45, "#d97757"), (0.7, "#10a37f"), (0.55, "#4285f4"))):
            x = w * (1 + 2 * i)
            hh = (size - 2 * w) * h
            p.setBrush(QColor(c))
            p.drawRoundedRect(x, size - w - hh, w, hh, w * 0.4, w * 0.4)
        p.end()
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

        self.palette = theme.resolve(self.settings.theme)
        self.window = MainWindow([(p.id, p.name) for p in self.providers], self.palette, self.settings)
        self.icon = make_icon()
        self.window.setWindowIcon(self.icon)
        app.setWindowIcon(self.icon)
        self.window.refresh_requested.connect(lambda: self.refresh(force=True))
        self.window.settings_requested.connect(self.open_settings)
        self.window.hide_requested.connect(self.hide_window)
        self.window.mode_changed.connect(lambda *_: self.save_settings())
        self.window.closeEvent = self._close_event

        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.icon)
            self._menu = self._build_menu()
            self.tray.setContextMenu(self._menu)
            self.tray.setToolTip(tr("AI Usage"))
            self.tray.activated.connect(self._tray_activated)
            self.tray.show()
        # Same menu on right-click in the window: the only menu on GNOME without a tray.
        self._window_menu = self._build_menu()
        self.window.setContextMenuPolicy(Qt.CustomContextMenu)
        self.window.customContextMenuRequested.connect(
            lambda pos: self._window_menu.exec(self.window.mapToGlobal(pos)))
        for keys, fn in ((("F5", "Ctrl+R"), lambda: self.refresh(force=True)),
                         (("Esc",), self.hide_window),
                         (("Ctrl+,",), self.open_settings),
                         (("Ctrl+E",), self.window.btn_expand.click),
                         (("Ctrl+Q",), self.quit)):
            for k in keys:
                QShortcut(QKeySequence(k), self.window, activated=fn)

        hints = QApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda *_: self.apply_theme())

        for snap in self.engine.snapshots.values():
            self.window.cards[snap.provider_id].update_snapshot(snap)
        self.restore_geometry()
        if not start_hidden or self.tray is None:
            self.window.show()

        self.local_timer = QTimer(self)
        self.local_timer.timeout.connect(lambda: self.refresh(local=True, quota=False))
        self.quota_timer = QTimer(self)
        self.quota_timer.timeout.connect(lambda: self.refresh(local=False, quota=True))
        self.tick = QTimer(self)  # keeps countdowns and "updated … ago" current
        self.tick.timeout.connect(self.repaint_cards)
        self.tick.start(30_000)
        self.apply_intervals()
        QTimer.singleShot(0, lambda: self.refresh(force=True))

    def _build_menu(self) -> QMenu:
        menu = QMenu()
        for text, fn in ((tr("Show / hide"), self.toggle_window),
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

    def _on_done(self, pid: str, kind: str, result):
        self.engine.end(pid, kind)
        if result is not None:
            snap = (self.engine.apply_local if kind == "local" else self.engine.apply_quota)(pid, result)
            self.window.cards[pid].update_snapshot(snap)
            self._maybe_notify(snap)  # local scans can reveal a limit hit before the next quota poll
        if not self.engine.busy:
            self.engine.save_cache()
        self._update_status()

    def _update_status(self):
        self.window.status.setText(tr("refreshing…") if self.engine.busy else "")
        if self.tray is not None:
            self.tray.setToolTip(tr("AI Usage") + "\n" + fmt.summary(self.engine.snapshots.values(), time.time()))

    def repaint_cards(self):
        for pid, snap in self.engine.snapshots.items():
            self.window.cards[pid].update_snapshot(snap)

    def _maybe_notify(self, snap):
        if self.tray is None:
            return
        for a in self.seen_alerts.take_new(alerts.pending([snap], self.settings.notify_threshold, time.time())):
            self.tray.showMessage(a["title"], a["body"], QSystemTrayIcon.Warning, 8000)

    # -- window / settings ----------------------------------------------
    def apply_theme(self):
        self.palette = theme.resolve(self.settings.theme)
        self.window.set_palette(self.palette)

    def open_settings(self):
        dlg = SettingsDialog(self.settings, autostart.supported(), self.window)
        dlg.setWindowIcon(self.icon)
        dlg.setStyleSheet(theme.stylesheet(self.palette) + f"QDialog {{ background: {self.palette.bg}; }}")
        if not dlg.exec():
            return
        before_top = self.settings.always_on_top
        dlg.apply_to(self.settings)
        if self.settings.always_on_top != before_top:
            self.window.apply_flags()
        try:
            if autostart.supported() and autostart.is_enabled() != self.settings.start_at_login:
                autostart.set_enabled(self.settings.start_at_login)
        except OSError:
            log.warning("could not change start-at-login")
        self.save_settings()
        self.apply_theme()
        self.apply_intervals()
        self.engine.next_quota_at.clear()
        self.refresh(force=True)

    def save_settings(self):
        g = self.window.geometry()
        self.settings.window = {"x": g.x(), "y": g.y(), "w": g.width(), "h": g.height()}
        try:
            settings_mod.save(self.settings)
        except OSError:
            log.warning("could not save settings")

    def restore_geometry(self):
        w = self.settings.window or {}
        self.window.resize(int(w.get("w", 360)), int(w.get("h", 520)))
        if "x" in w and "y" in w:
            # Ignored by most Wayland compositors; works on Windows and X11.
            self.window.move(int(w["x"]), int(w["y"]))

    def toggle_window(self):
        if self.window.isVisible():
            self.hide_window()
        else:
            self.window.show()
            self.window.raise_()
            self.window.activateWindow()

    def hide_window(self):
        self.save_settings()
        if self.tray is not None and self.settings.minimize_to_tray:
            self.window.hide()
        else:
            self.quit()

    def _close_event(self, e):
        e.ignore()
        self.hide_window()

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle_window()

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
    parser = argparse.ArgumentParser(prog="aiusage", description="AI usage desktop widget")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--hidden", action="store_true", help="start hidden in the tray")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    parser.add_argument("--allow-multiple", action="store_true", help="skip the single-instance check")
    parser.add_argument("--xwayland", action="store_true",
                        help="on Wayland, run through XWayland so keep-above and saved position work")
    parser.add_argument("--widget-json", action="store_true",
                        help="refresh (quota only when due) and print display-ready JSON for the Plasma widget")
    parser.add_argument("--print", dest="print_json", action="store_true",
                        help="collect once and print the snapshot as JSON (no window)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.print_json:
        return print_once()
    if args.widget_json:
        return widget_json()

    if args.xwayland and os.environ.get("WAYLAND_DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"
    # One widget per user session. QLockFile checks the owner PID, so a crashed run's lock is taken over.
    lock_dir = paths.cache_dir()
    lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = QLockFile(str(lock_dir / "instance.lock"))
    lock.setStaleLockTime(5000)
    if not args.allow_multiple and not lock.tryLock(100):
        print("AI Usage Widget is already running (use the tray icon, or pass --allow-multiple).",
              file=sys.stderr)
        return 1
    app = QApplication(sys.argv[:1])
    app.setApplicationName("AI Usage Widget")
    app.setDesktopFileName("ai-usage-widget")
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


def widget_json() -> int:
    """One refresh for the Plasma widget: local always, quota only when its interval is due."""
    import json
    from concurrent.futures import ThreadPoolExecutor

    from . import viewmodel

    s = settings_mod.load()
    set_language(s.language)
    eng = Engine(s, [P(s) for P in ALL], mark_stale=False)
    new_alerts = []
    lock_dir = paths.cache_dir()
    lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = QLockFile(str(lock_dir / "widget-refresh.lock"))
    if lock.tryLock(60_000):  # another widget instance refreshing: wait for it, then reuse
        try:
            eng = Engine(s, [P(s) for P in ALL], mark_stale=False)  # reload what it wrote
            now = time.time()
            with ThreadPoolExecutor(6) as ex:
                local = {pid: ex.submit(eng.run_local, pid) for pid in eng.providers}
                quota = {pid: ex.submit(eng.run_quota, pid) for pid in eng.providers
                         if eng.quota_due(pid, now)}
            for pid, f in local.items():
                eng.apply_local(pid, f.result())
            for pid, f in quota.items():
                eng.apply_quota(pid, f.result(), now)
            eng.save_cache()
            new_alerts = alerts.Seen().take_new(
                alerts.pending(eng.snapshots.values(), s.notify_threshold, time.time()))
        finally:
            lock.unlock()
    view = viewmodel.widget_view(eng.snapshots.values(), time.time())
    view["notify"] = [{"title": a["title"], "text": a["body"]} for a in new_alerts]
    sys.stdout.write(json.dumps(view, ensure_ascii=False))
    sys.stdout.flush()
    return 0
