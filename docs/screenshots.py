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
# Relative: Qt splits the platform options at ":", which a Windows drive letter contains.
os.environ["QT_QPA_PLATFORM"] = f"offscreen:configfile={Path(os.path.relpath(_screen)).as_posix()}"
if sys.platform == "win32":  # offscreen finds no fonts of its own there
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_SCALE_FACTOR", "2")
os.environ["LANG"] = os.environ["LC_ALL"] = "C.UTF-8"  # English UI
# Keep the real settings and cache untouched.
for var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "APPDATA", "LOCALAPPDATA"):
    os.environ[var] = _tmp

from PySide6.QtCore import QObject, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen  # noqa: E402
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


DAY_WEIGHTS = (5, 3, 6, 2, 4, 7, 3)  # today first: a believable week with busy and quiet days


def local(models: list[tuple[str, int, int, int, int]]) -> LocalUsage:
    """models: (id, input, output, cache read, cache write) per busy-day unit."""
    events = [UsageEvent(NOW - (i + 1) * 1200 - day * 86400, m,
                         Tokens(input=inp * k, output=out * k, cache_read=cr * k, cache_write=cw * k))
              for day, k in enumerate(DAY_WEIGHTS)
              for i, (m, inp, out, cr, cw) in enumerate(models)]
    per_day = sum(inp + out + cr + cw for _m, inp, out, cr, cw in models)
    daily = []
    for d in range(13, -1, -1):
        t = time.localtime(NOW - d * 86400)
        daily.append([time.strftime("%Y-%m-%d", t), per_day * (DAY_WEIGHTS[d] if d < 7 else 2)])
    return LocalUsage(State.OK, aggregate(events, NOW), updated_at=NOW - 20, files=42, daily=daily)


def demo() -> list[ProviderSnapshot]:
    claude = ProviderSnapshot("claude", "Claude Code",
        local([("claude-opus-5-5", 2_400, 410_000, 9_800_000, 260_000),
               ("claude-sonnet-5-5", 900, 120_000, 2_600_000, 90_000)]),
        Quota(State.OK, [QuotaWindow("five_hour", "5-hour session", 34.0, NOW + 2.6 * H, 300),
                         QuotaWindow("seven_day", "Weekly", 61.0, NOW + 3.2 * 24 * H, 10080)],
              plan="Max", updated_at=NOW - 40))
    codex = ProviderSnapshot("codex", "Codex",
        local([("gpt-5.5", 380_000, 95_000, 2_100_000, 0)]),
        Quota(State.OK, [QuotaWindow("codex:primary", "5-hour session", 12.0, NOW + 4.1 * H, 300),
                         QuotaWindow("codex:secondary", "Weekly", 48.0, NOW + 5.5 * 24 * H, 10080)],
              plan="plus", updated_at=NOW - 40))
    # Antigravity as its running language server reports it: limits per group, models per group.
    ag_windows = [QuotaWindow("antigravity:gemini-5h", "5-hour session · Gemini", 9.0, NOW + 3.7 * H, 300),
                  QuotaWindow("antigravity:gemini-weekly", "Weekly · Gemini", 27.0, NOW + 4.4 * 24 * H, 10080),
                  QuotaWindow("antigravity:3p-5h", "5-hour session · Claude and GPT", 18.0, NOW + 1.2 * H, 300),
                  QuotaWindow("antigravity:3p-weekly", "Weekly · Claude and GPT", 44.0, NOW + 5.1 * 24 * H, 10080),
                  QuotaWindow("antigravity:argon-weekly", "Weekly · Gemini 4 Argon", 31.0, NOW + 3.9 * 24 * H, 10080)]
    pair = {"g": ["antigravity:gemini-5h", "antigravity:gemini-weekly"],
            "p": ["antigravity:3p-5h", "antigravity:3p-weekly"]}
    ag = ProviderSnapshot("antigravity", "Antigravity",
        local([("gemini-3.8-flash-n", 260_000, 14_000, 900_000, 0),
               ("gemini-4-argon-trial", 90_000, 12_000, 700_000, 0)]),
        Quota(State.OK, ag_windows, plan="Google AI Pro", updated_at=NOW - 30, extra={"models": [
            {"name": "Gemini 4 Argon", "windows": ["antigravity:argon-weekly"]},
            {"name": "Gemini 3.8 Flash", "windows": pair["g"]},
            {"name": "Claude Opus 5.5", "windows": pair["p"]},
            {"name": "Claude Sonnet 5.5", "windows": pair["p"]}]}))
    return [claude, codex, ag]


def settle(app, n=40):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.01)


def make_popup(palette: theme.Palette):
    settings = Settings()
    settings.pinned["antigravity"] = "Gemini 3.8 Flash"  # a model with both rings
    backend = Backend(settings, palette)
    backend.set_settings_form(settings_form.form(settings, True))
    popup = Popup(backend, docked=False)
    popup.show()
    backend.set_view(viewmodel.widget_view(demo(), NOW))
    return popup


def shot(app, popup: Popup, name: str, page: str, full: bool = True, **props):
    """One page of the popup. `full` shows the whole page instead of the scrolling 660 px."""
    content = popup.window.findChild(QObject, "popupContent")
    if page == "settings":
        popup.open_settings()
    else:
        content.setProperty("page", page)
    for k, v in props.items():
        content.setProperty(k, v)
    settle(app)
    if full:
        popup.window.setHeight(int(content.property("implicitHeight")))
        settle(app)
    popup.window.grabWindow().save(str(OUT / name))


def taskbar(palette: theme.Palette, dark: bool, name: str):
    """The right end of a Windows 11 taskbar at its real proportions, with the demo's ring icon
    among the usual tray icons (drawn here, so the image holds no real desktop)."""
    w, h, scale = 300, 48, 2  # logical px; the taskbar is 48 px high, tray icons 16 px
    bar, fg = (QColor("#1c1c1c"), QColor("#ffffff")) if dark else (QColor("#eeeeee"), QColor("#1a1a1a"))
    img = QImage(w * scale, h * scale, QImage.Format_ARGB32)
    img.fill(bar)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(scale, scale)
    edge = QColor(fg)
    edge.setAlphaF(0.12)
    p.setPen(QPen(edge, 1))
    p.drawLine(QPointF(0, 0.5), QPointF(w, 0.5))
    cy = h / 2
    pen = QPen(fg, 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPolyline([QPointF(14, cy + 2), QPointF(18, cy - 2), QPointF(22, cy + 2)])  # hidden icons
    ring = viewmodel.widget_view(demo(), NOW)["ring"]
    hover = QColor(fg)
    hover.setAlphaF(0.08)
    p.setPen(Qt.NoPen)
    p.setBrush(hover)  # the pointer rests on it
    p.drawRoundedRect(QRectF(36, cy - 16, 32, 32), 4, 4)
    pm = make_ring_icon(ring, True, palette).pixmap(16 * scale, 16 * scale)
    p.drawPixmap(QRectF(44, cy - 8, 16, 16), pm, QRectF(pm.rect()))
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    x = 92  # wifi: three arcs over a dot
    for r in (3.5, 7, 10.5):
        p.drawArc(QRectF(x - r, cy + 5 - r, 2 * r, 2 * r), 45 * 16, 90 * 16)
    p.setBrush(fg)
    p.drawEllipse(QPointF(x, cy + 4.5), 1, 1)
    p.setBrush(Qt.NoBrush)
    x = 116  # speaker with two waves
    p.drawPolygon([QPointF(x - 6, cy - 2.5), QPointF(x - 3, cy - 2.5), QPointF(x + 1, cy - 6),
                   QPointF(x + 1, cy + 6), QPointF(x - 3, cy + 2.5), QPointF(x - 6, cy + 2.5)])
    for r in (3.5, 6.5):
        p.drawArc(QRectF(x + 1 - r, cy - r, 2 * r, 2 * r), -50 * 16, 100 * 16)
    x = 136  # battery, about four fifths full
    p.drawRoundedRect(QRectF(x, cy - 4.5, 16, 9), 2, 2)
    p.drawLine(QPointF(x + 17.5, cy - 1.5), QPointF(x + 17.5, cy + 1.5))
    p.setPen(Qt.NoPen)
    p.setBrush(fg)
    p.drawRoundedRect(QRectF(x + 2, cy - 2.5, 10, 5), 1, 1)
    font = QFont("Segoe UI")
    font.setPixelSize(12)
    p.setFont(font)
    p.setPen(fg)
    clock = QRectF(170, 0, 110, h)
    p.drawText(clock.adjusted(0, 0, 0, -h / 2 + 1), Qt.AlignRight | Qt.AlignBottom, "2:32 PM")
    p.drawText(clock.adjusted(0, h / 2 + 2, 0, 0), Qt.AlignRight | Qt.AlignTop, "10/30/2026")
    p.end()
    img.save(str(OUT / name))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    font = QFont(app.font())
    app.setFont(font)
    dark, light = make_popup(theme.DARK), make_popup(theme.LIGHT)
    shot(app, dark, "limits-dark.png", "limits")
    shot(app, light, "limits-light.png", "limits")
    shot(app, dark, "tokens-dark.png", "tokens", tokPeriod="7d")
    shot(app, light, "tokens-light.png", "tokens", tokPeriod="7d")
    shot(app, dark, "settings-dark.png", "settings")
    shot(app, light, "settings-light.png", "settings")
    taskbar(theme.DARK, True, "taskbar-dark.png")
    taskbar(theme.LIGHT, False, "taskbar-light.png")
    for f in sorted(OUT.glob("*.png")):
        print(f.relative_to(ROOT), QImage(str(f)).size().toTuple())


if __name__ == "__main__":
    main()
