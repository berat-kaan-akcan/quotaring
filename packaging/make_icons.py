"""Render the app icon (same drawing as the tray icon) to PNG/ICO files for packaging."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from aiusage.app import make_icon  # noqa: E402

out = Path(__file__).resolve().parent / "icons"
app = QGuiApplication([])
icon = make_icon()
out.mkdir(exist_ok=True)
for size in (16, 32, 48, 64, 128, 256):
    icon.pixmap(QSize(size, size)).save(str(out / f"ai-usage-widget-{size}.png"))
icon.pixmap(QSize(256, 256)).save(str(out / "ai-usage-widget.ico"))
print("icons written to", out)
