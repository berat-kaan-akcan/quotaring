"""The tray popup: a QML window over the display-ready view model (quotaring/viewmodel.py)."""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import Property, QObject, QRect, QTimer, QUrl, Signal, Slot, qVersion
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from .. import paths
from .theme import Palette

log = logging.getLogger("quotaring")

QML_DIR = Path(__file__).with_name("qml")
SYSTEM_QML_DIRS = ("/usr/lib/qt6/qml", "/usr/lib64/qt6/qml",
                   "/usr/lib/x86_64-linux-gnu/qt6/qml", "/usr/lib/aarch64-linux-gnu/qt6/qml")
MARGIN = 8
# A tray click right after the popup hid itself (it lost focus to that click) must not reopen it.
REOPEN_GUARD = 0.35
# KWin may take focus back from a freshly mapped popup (seen on its first show); that is not a
# click elsewhere, so within this time the popup asks for focus again instead of closing.
SETTLE_TIME = 0.5
PROBE_TIMEOUT_MS = 300


def layer_shell_import_dir() -> str | None:
    """An import dir that provides org.kde.layershell to the running Qt, or None.

    PySide6 from pip brings its own Qt, so the system's plugin is only used when it was built
    for the same Qt version. Only that one module is exposed (via a symlink in the cache dir):
    adding the whole system import path would mix the system's QtQuick plugins into pip's Qt.
    """
    if sys.platform != "linux" or not os.environ.get("WAYLAND_DISPLAY"):
        return None
    if not os.environ.get("QT_QPA_PLATFORM", "wayland").startswith("wayland"):
        return None  # xcb (XWayland), offscreen (tests)
    for base in SYSTEM_QML_DIRS:
        module = Path(base) / "org" / "kde" / "layershell"
        if not (module / "qmldir").is_file():
            continue
        libdir = Path(base).parent.parent  # /usr/lib/qt6/qml -> /usr/lib
        built_for = {p.name.split(".so.", 1)[1] for p in libdir.glob("libQt6Core.so.6.*")}
        if qVersion() not in built_for:
            log.info("layer-shell module is for Qt %s, running Qt %s", built_for, qVersion())
            return None
        link_root = paths.cache_dir() / "qml"
        link = link_root / "org" / "kde" / "layershell"
        try:
            link.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if link.is_symlink() and link.resolve() != module.resolve():
                link.unlink()
            if not link.exists():
                link.symlink_to(module, target_is_directory=True)
        except OSError:
            log.warning("could not expose the layer-shell module")
            return None
        return str(link_root)
    return None


def centered_left(x: int, width: int, area_x: int, area_width: int) -> int:
    """Left edge of a popup centred on x, kept MARGIN inside the area."""
    return max(area_x + MARGIN, min(x - width // 2, area_x + area_width - width - MARGIN))


def panel_at_top(screen) -> bool:
    """True when the screen's reserved area (the panel) is at the top."""
    a, g = screen.availableGeometry(), screen.geometry()
    return a.top() > g.top() and a.bottom() >= g.bottom()


class Backend(QObject):
    """What the QML sees as `backend`: the view, refresh state, palette and popup preferences."""

    viewChanged = Signal()
    busyChanged = Signal()
    paletteChanged = Signal()
    prefsChanged = Signal()
    refreshRequested = Signal()
    settingsRequested = Signal()
    hideRequested = Signal()
    focusLostRequested = Signal()
    quitRequested = Signal()
    testNotificationRequested = Signal()
    updateRequested = Signal()
    updateChanged = Signal()
    prefsSaved = Signal()
    settingsFormChanged = Signal()
    settingsSaved = Signal("QVariantMap")

    PREFS = {"showRemaining": ("show_remaining", bool)}

    def __init__(self, settings, palette: Palette):
        super().__init__()
        self.settings = settings
        self._view = None
        self._busy = False
        self._palette = palette
        self._form = {}
        self._update = {}

    def set_settings_form(self, form: dict):
        self._form = form
        self.settingsFormChanged.emit()

    @Property("QVariantMap", notify=settingsFormChanged)
    def settingsForm(self):
        return self._form

    @Slot("QVariantMap")
    def saveSettings(self, values):
        self.settingsSaved.emit(values)

    @Slot()
    def testNotification(self):
        self.testNotificationRequested.emit()

    def set_update(self, update: dict):
        """The new-version banner: {} hides it."""
        self._update = update
        self.updateChanged.emit()

    @Property("QVariantMap", notify=updateChanged)
    def updateInfo(self):
        return self._update

    @Slot()
    def installUpdate(self):
        self.updateRequested.emit()

    def set_view(self, view: dict):
        self._view = view
        self.viewChanged.emit()

    def set_busy(self, busy: bool):
        if busy != self._busy:
            self._busy = busy
            self.busyChanged.emit()

    def set_palette(self, palette: Palette):
        self._palette = palette
        self.paletteChanged.emit()

    def notify_settings_changed(self):
        self.prefsChanged.emit()

    @Property("QVariant", notify=viewChanged)
    def view(self):
        return self._view

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy

    @Property("QVariantMap", notify=paletteChanged)
    def palette(self):
        return vars(self._palette)

    @Property("QVariantMap", notify=prefsChanged)
    def prefs(self):
        prefs = {key: getattr(self.settings, attr) for key, (attr, _t) in self.PREFS.items()}
        prefs["pinned"] = dict(self.settings.pinned)
        prefs["order"] = list(self.settings.card_order)
        return prefs

    @Slot("QVariant")
    def setCardOrder(self, order):
        """The provider cards as the user arranged them (by dragging)."""
        self.settings.card_order = list(order or [])
        self.settings.clamp()
        self.prefsChanged.emit()
        self.prefsSaved.emit()

    @Slot(str, str)
    def pin(self, provider, label):
        """Show this limit on the provider's ring; pinning the pinned one again unpins it."""
        if self.settings.pinned.get(provider) == label:
            self.settings.pinned.pop(provider, None)
        else:
            self.settings.pinned[provider] = label
        self.settings.clamp()
        self.prefsChanged.emit()
        self.prefsSaved.emit()

    @Slot(str, "QVariant")
    def setPref(self, key, value):
        if key not in self.PREFS:
            return
        attr, typ = self.PREFS[key]
        setattr(self.settings, attr, typ(value))
        self.settings.clamp()
        self.prefsChanged.emit()
        self.prefsSaved.emit()

    @Slot()
    def refresh(self):
        self.refreshRequested.emit()

    @Slot()
    def openSettings(self):
        self.settingsRequested.emit()

    @Slot()
    def hide(self):
        self.hideRequested.emit()

    @Slot()
    def focusLost(self):
        self.focusLostRequested.emit()

    @Slot()
    def quit(self):
        self.quitRequested.emit()


class Popup:
    """Loads the QML window and opens it by the panel: layer-shell on Wayland, placed by hand elsewhere.

    `docked=False` (no system tray) makes it an ordinary window that stays open."""

    def __init__(self, backend: Backend, docked: bool):
        self.docked = docked
        self.engine = QQmlApplicationEngine()
        backend.setParent(self.engine)  # outlives the QML that binds to it, also at exit
        self.engine.rootContext().setContextProperty("backend", backend)
        self.layer = False
        layer_dir = layer_shell_import_dir() if docked else None
        if layer_dir:
            self.engine.addImportPath(layer_dir)
            screen = QGuiApplication.primaryScreen()
            self.layer = self._load("LayerPopupWindow.qml", atTop=bool(screen and panel_at_top(screen)))
            if not self.layer:
                log.warning("layer-shell popup failed to load; using a plain window")
        if not self.layer and not self._load("PopupWindow.qml"):
            raise RuntimeError("could not load the popup QML")
        self.window = self.engine.rootObjects()[-1]
        self._hidden_at = 0.0
        self._shown_at = 0.0
        backend.focusLostRequested.connect(self.focus_lost)
        # Layer-shell: open above the clicked tray icon, located through KWin (see cursor_probe).
        self.probe = None
        self._waiting = QTimer()
        self._waiting.setSingleShot(True)
        self._waiting.setInterval(PROBE_TIMEOUT_MS)
        self._waiting.timeout.connect(self.show)  # no answer: open in the corner
        if self.layer:
            from .cursor_probe import CursorProbe
            self.probe = CursorProbe()
            self.probe.reported.connect(self._show_above)
        elif docked:
            self.window.heightChanged.connect(lambda *_: self._place() if self.window.isVisible() else None)

    def _load(self, name: str, **props) -> bool:
        before = len(self.engine.rootObjects())
        self.engine.setInitialProperties({"docked": self.docked, **props})
        self.engine.load(QUrl.fromLocalFile(str(QML_DIR / name)))
        return len(self.engine.rootObjects()) > before

    def open_settings(self):
        """Show the popup on its Settings page."""
        if not self.is_visible():
            self.show()  # opens on Limits
        self.content().setProperty("page", "settings")

    def content(self):
        return self.window.findChild(QObject, "popupContent")

    def is_visible(self) -> bool:
        return self.window.isVisible()

    def show(self):
        if self.docked and not self.layer:
            self._place()
        self._shown_at = time.monotonic()
        self.window.show()
        self.window.raise_()
        self.window.requestActivate()

    def focus_lost(self):
        if time.monotonic() - self._shown_at < SETTLE_TIME:
            self.window.requestActivate()
        else:
            self.hide()

    def hide(self):
        self._hidden_at = time.monotonic()
        self.window.hide()

    def toggle(self):
        if self.window.isVisible() or self._waiting.isActive():
            self._waiting.stop()
            self.hide()
        elif time.monotonic() - self._hidden_at > REOPEN_GUARD:
            if self.probe is not None and self.probe.request():
                self._waiting.start()  # _show_above when KWin answers
            else:
                self.show()

    def _show_above(self, x: int, screen: QRect):
        if not self._waiting.isActive():
            return  # late answer: already opened in the corner, or closed again
        self._waiting.stop()
        left = centered_left(x, self.window.width(), screen.x(), screen.width())
        self.window.setProperty("rightMargin", screen.x() + screen.width() - left - self.window.width())
        self.show()

    def _place(self):
        """Above the clicked icon: centred on the cursor, inside the screen, by the panel.

        X11, Windows and XWayland, where the cursor position and window placement are available."""
        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        a = screen.availableGeometry()
        w, h = self.window.width(), self.window.height()
        y = a.top() + MARGIN if panel_at_top(screen) else a.bottom() - h - MARGIN
        self.window.setPosition(centered_left(cursor.x(), w, a.x(), a.width()), y)
