"""Render the app icon (same drawing as the tray icon) to PNG/ICO files for packaging."""

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QBuffer, QIODevice, QSize  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from quotaring.app import make_icon  # noqa: E402

out = Path(__file__).resolve().parent / "icons"
app = QGuiApplication([])
icon = make_icon()
out.mkdir(exist_ok=True)
for size in (16, 32, 48, 64, 128, 256):
    icon.pixmap(QSize(size, size)).save(str(out / f"quotaring-{size}.png"))

# Multi-size .ico (PNG entries, Windows Vista+): Qt's writer stores a single size only.
ico_sizes = (16, 24, 32, 48, 64, 128, 256)


def png_bytes(n: int) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    icon.pixmap(QSize(n, n)).save(buf, "PNG")
    return bytes(buf.data())


images = [png_bytes(n) for n in ico_sizes]
header = struct.pack("<HHH", 0, 1, len(images))
offset = 6 + 16 * len(images)
entries = b""
for n, data in zip(ico_sizes, images):
    entries += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), offset)
    offset += len(data)
(out / "quotaring.ico").write_bytes(header + entries + b"".join(images))
print("icons written to", out)
