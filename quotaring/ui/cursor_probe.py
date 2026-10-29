"""Where the tray icon was clicked, on KDE Wayland.

Qt drops the click position the tray passes in StatusNotifierItem.Activate, and Wayland clients
cannot read the global cursor position. KWin scripts can: a one-line script is loaded and run
over D-Bus, and calls back into this object with the cursor and its screen.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import ClassInfo, QObject, QRect, Signal, Slot
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

from .. import paths

log = logging.getLogger("quotaring")

SERVICE = "org.quotaring.Widget"
PATH = "/Cursor"
INTERFACE = "org.quotaring.Cursor"
SCRIPT_NAME = "quotaring-cursor"
SCRIPT = (f'var s = workspace.activeScreen.geometry; callDBus("{SERVICE}", "{PATH}", "{INTERFACE}", "report", '
          '[workspace.cursorPos.x, workspace.cursorPos.y, s.x, s.y, s.width, s.height].join(","));\n')


@ClassInfo({"D-Bus Interface": INTERFACE})
class CursorProbe(QObject):
    reported = Signal(int, QRect)  # cursor x, the screen it is on (logical coordinates)

    def __init__(self):
        super().__init__()
        bus = QDBusConnection.sessionBus()
        self.available = (bus.isConnected() and bus.interface().isServiceRegistered("org.kde.KWin").value()
                          and bus.registerService(SERVICE)
                          and bus.registerObject(PATH, self, QDBusConnection.ExportAllSlots))
        if not self.available:
            return
        self.script = paths.cache_dir() / "kwin-cursor.js"
        try:
            self.script.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not self.script.is_file() or self.script.read_text() != SCRIPT:
                self.script.write_text(SCRIPT)
        except OSError:
            log.warning("could not write the KWin cursor script")
            self.available = False

    def request(self) -> bool:
        """Ask KWin for the cursor position; `reported` follows shortly. False if it cannot."""
        if not self.available:
            return False
        scripting = QDBusInterface("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting")
        scripting.call("unloadScript", SCRIPT_NAME)  # a run that failed half way
        reply = scripting.call("loadScript", str(self.script), SCRIPT_NAME)
        if reply.type() != QDBusMessage.ReplyMessage or not reply.arguments():
            log.info("KWin did not load the cursor script")
            return False
        script_id = reply.arguments()[0]
        QDBusInterface("org.kde.KWin", f"/Scripting/Script{script_id}", "org.kde.kwin.Script").call("run")
        scripting.call("unloadScript", SCRIPT_NAME)
        return True

    @Slot(str)
    def report(self, text: str):
        try:
            x, _y, sx, sy, sw, sh = (int(float(v)) for v in text.split(","))
        except ValueError:
            return
        self.reported.emit(x, QRect(sx, sy, sw, sh))
