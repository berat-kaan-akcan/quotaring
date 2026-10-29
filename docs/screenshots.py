"""Render the README images from synthetic demo data (no real provider data is read).

    python docs/screenshots.py      -> docs/images/*.png
"""

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp()
# A large virtual screen scaled 2x (QT_SCALE_FACTOR), so the images are sharp on HiDPI displays.
_screen = Path(_tmp, "screen.json")
_screen.write_text('{"screens": [{"name": "s", "x": 0, "y": 0, "width": 2000, "height": 2000,'
                   ' "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1}]}')
os.environ["QT_QPA_PLATFORM"] = f"offscreen:configfile={_screen}"
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_SCALE_FACTOR", "2")
os.environ["LANG"] = os.environ["LC_ALL"] = "C.UTF-8"  # English UI
# Keep the real settings and cache untouched.
for var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "APPDATA", "LOCALAPPDATA"):
    os.environ[var] = _tmp

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402,F401  (rootObjects() then yields QQuickWindow)
from PySide6.QtWidgets import QApplication  # noqa: E402

from quotaring import viewmodel  # noqa: E402
from quotaring.aggregate import aggregate  # noqa: E402
from quotaring.app import make_ring_icon  # noqa: E402
from quotaring.model import LocalUsage, ProviderSnapshot, Quota, QuotaWindow, State, Tokens, UsageEvent  # noqa: E402
from quotaring.settings import Settings  # noqa: E402
from quotaring.ui import settings_form, theme  # noqa: E402
from quotaring.ui.popup import Backend, Popup  # noqa: E402

OUT = ROOT / "docs" / "images"
NOW = time.time()
H = 3600


def local(daily_scale: int, models: list[tuple[str, int, int]]) -> LocalUsage:
    events = [UsageEvent(NOW - (i + 1) * 1800 - day * 86400, m,
                         Tokens(input=inp * k, output=out * k, cache_read=inp * k * 6))
              for day, k in enumerate((1, 3, 2, 4, 2, 5, 3))
              for i, (m, inp, out) in enumerate(models)]
    days = time.localtime(NOW)
    daily = []
    for d in range(13, -1, -1):
        t = time.localtime(NOW - d * 86400)
        daily.append([time.strftime("%Y-%m-%d", t), daily_scale * (3 + (d * 7 + days.tm_mday) % 9)])
    return LocalUsage(State.OK, aggregate(events, NOW), updated_at=NOW - 20, files=42, daily=daily)


def demo() -> list[ProviderSnapshot]:
    claude = ProviderSnapshot("claude", "Claude Code",
        local(180_000, [("claude-opus-5-5", 48_000, 9_100), ("claude-sonnet-5-5", 22_000, 4_300)]),
        Quota(State.OK, [QuotaWindow("five_hour", "5-hour session", 34.0, NOW + 2.6 * H, 300),
                         QuotaWindow("seven_day", "Weekly", 61.0, NOW + 3.2 * 24 * H, 10080)],
              plan="Max", updated_at=NOW - 40))
    codex = ProviderSnapshot("codex", "Codex",
        local(90_000, [("gpt-5-codex", 31_000, 6_200)]),
        Quota(State.OK, [QuotaWindow("codex:primary", "5-hour session", 12.0, NOW + 4.1 * H, 300),
                         QuotaWindow("codex:secondary", "Weekly", 48.0, NOW + 5.5 * 24 * H, 10080)],
              plan="plus", updated_at=NOW - 40))
    ag = ProviderSnapshot("antigravity", "Antigravity",
        local(40_000, [("gemini-3-pro", 12_000, 2_500)]),
        Quota(State.OK, [QuotaWindow("antigravity:gemini", "Gemini 3 Pro", 22.0, NOW + 3.7 * H),
                         QuotaWindow("antigravity:claude", "Claude Sonnet 5.5", 81.0, NOW + 1.2 * H)],
              plan="Google AI Pro", updated_at=NOW - 300))
    return [claude, codex, ag]


def settle(app, n=40):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.01)


def popup_shot(app, palette: theme.Palette, name: str) -> Popup:
    settings = Settings()
    backend = Backend(settings, palette)
    popup = Popup(backend, docked=False)
    popup.show()
    backend.set_view(viewmodel.widget_view(demo(), NOW))
    settle(app)
    popup.window.grabWindow().save(str(OUT / name))
    return popup, backend, settings


def tray_strip(palette: theme.Palette, name: str):
    """The ring icon at panel size in three states, on a panel-coloured strip."""
    rings = [{"available": True, "used": 34, "remaining": 66, "level": "ok", "limited": False},
             {"available": True, "used": 81, "remaining": 19, "level": "warn", "limited": False},
             {"available": True, "used": 100, "remaining": 0, "level": "bad", "limited": True}]
    size, pad, scale = 32, 20, 3
    img = QImage((pad + (size + pad) * len(rings)) * scale, (size + 2 * pad) * scale, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(scale, scale)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(palette.bg))
    p.drawRoundedRect(QRectF(0, 0, img.width() / scale, img.height() / scale), 10, 10)
    for i, r in enumerate(rings):
        pm = make_ring_icon(r, True, palette).pixmap(size * scale, size * scale)
        p.drawPixmap(QRectF(pad + i * (size + pad), pad, size, size), pm, QRectF(pm.rect()))
    p.end()
    img.save(str(OUT / name))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    font = QFont(app.font())
    app.setFont(font)
    keep = [popup_shot(app, theme.DARK, "popup-dark.png"), popup_shot(app, theme.LIGHT, "popup-light.png")]
    popup, backend, settings = keep[0]
    backend.set_settings_form(settings_form.form(settings, True))
    popup.open_settings()
    settle(app)
    popup.settings_window.grabWindow().save(str(OUT / "settings-dark.png"))
    tray_strip(theme.DARK, "tray-dark.png")
    for f in sorted(OUT.glob("*.png")):
        print(f.relative_to(ROOT), QImage(str(f)).size().toTuple())


if __name__ == "__main__":
    main()
