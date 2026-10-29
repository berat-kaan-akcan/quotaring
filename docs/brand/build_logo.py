"""Build the QuotaRing logo files (SVG) from their geometry.

    QT_QPA_PLATFORM=offscreen python docs/brand/build_logo.py      -> docs/brand/*.svg

The symbol is a Q drawn as a gauge: a ring three quarters full whose tail is the needle.
Canvas 256 x 256; the wordmark is Noto Sans Bold (SIL OFL) converted to outlines.
"""

import sys
from math import cos, radians, sin
from pathlib import Path

from PySide6.QtGui import QFont, QGuiApplication, QPainterPath

OUT = Path(__file__).resolve().parent
NIGHT, INK, INK_DARK = "#18191C", "#1D1C1A", "#ECEBE8"
# Accent colours, as in quotaring/ui/theme.py ACCENTS: (light background, dark background).
ACCENTS = {"slate": ("#3F5468", "#A9B8C8"), "ink": (INK, INK_DARK), "amber": ("#A15F00", "#F2B544")}
MAIN, MAIN_DARK = ACCENTS["slate"]  # the default; used for the logo files


def mark(c=125.0, r=80.0, w=36.0, tail=116.0) -> str:
    """Ring from 12 o'clock clockwise to 9 o'clock, plus the tail at 45 degrees (filled outlines)."""
    def pt(rr, a):
        return f"{c + rr * cos(radians(a)):.2f} {c + rr * sin(radians(a)):.2f}"
    ro, ri, h = r + w / 2, r - w / 2, w / 2
    ring = (f"M{pt(ro, -90)}A{ro} {ro} 0 1 1 {pt(ro, 180)}A{h} {h} 0 0 1 {pt(ri, 180)}"
            f"A{ri} {ri} 0 1 0 {pt(ri, -90)}A{h} {h} 0 0 1 {pt(ro, -90)}Z")

    def side(rr, s):  # s = -1 / +1: the two long edges of the tail
        x = c + rr * cos(radians(45)) + s * h * cos(radians(135))
        y = c + rr * sin(radians(45)) + s * h * sin(radians(135))
        return f"{x:.2f} {y:.2f}"
    # Starts on the ring's centre line so its rounded end hides inside the ring (no lump).
    tail_path = (f"M{side(r, -1)}L{side(tail, -1)}A{h} {h} 0 0 1 {side(tail, 1)}"
                 f"L{side(r, 1)}A{h} {h} 0 0 1 {side(r, -1)}Z")
    return ring + tail_path


SYMBOL = mark()
SYMBOL_SMALL = mark(c=124, r=74, w=50, tail=106)  # heavier cut for 16-32 px


def wordmark(px: int):
    font = QFont("Noto Sans")
    font.setBold(True)
    font.setPixelSize(px)
    font.setLetterSpacing(QFont.PercentageSpacing, 99)
    path = QPainterPath()
    path.addText(0, 0, font, "QuotaRing")
    out, i = [], 0
    while i < path.elementCount():
        e = path.elementAt(i)
        if e.isMoveTo():
            out.append(f"M{e.x:.2f} {e.y:.2f}")
            i += 1
        elif e.isLineTo():
            out.append(f"L{e.x:.2f} {e.y:.2f}")
            i += 1
        else:
            c2, end = path.elementAt(i + 1), path.elementAt(i + 2)
            out.append(f"C{e.x:.2f} {e.y:.2f} {c2.x:.2f} {c2.y:.2f} {end.x:.2f} {end.y:.2f}")
            i += 3
    return "".join(out) + "Z", path.boundingRect()


def svg(name: str, viewbox: str, body: str) -> None:
    (OUT / f"{name}.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" role="img" aria-label="QuotaRing">'
        f"<title>QuotaRing</title>{body}</svg>\n")


def main():
    QGuiApplication(sys.argv)
    svg("quotaring-symbol", "0 0 256 256", f'<path fill="{MAIN}" d="{SYMBOL}"/>')
    svg("quotaring-symbol-small", "0 0 256 256", f'<path fill="{MAIN}" d="{SYMBOL_SMALL}"/>')
    svg("quotaring-symbol-black", "0 0 256 256", f'<path fill="#000" d="{SYMBOL}"/>')
    svg("quotaring-symbol-white", "0 0 256 256", f'<path fill="#fff" d="{SYMBOL}"/>')

    # Horizontal: wordmark optically centred on the ring, gap about one tail width.
    text, box = wordmark(124)
    x0 = 256 + 36 - box.left()
    y0 = 128 - (box.top() + box.bottom()) / 2 + 6
    width = x0 + box.right() + 20
    for name, mark_color, text_color in (("horizontal", MAIN, INK), ("horizontal-dark", MAIN_DARK, INK_DARK),
                                         ("horizontal-black", "#000", "#000"),
                                         ("horizontal-white", "#fff", "#fff")):
        svg(f"quotaring-{name}", f"0 0 {width:.0f} 256",
            f'<path fill="{mark_color}" d="{SYMBOL}"/>'
            f'<path fill="{text_color}" transform="translate({x0:.2f} {y0:.2f})" d="{text}"/>')

    # Stacked
    text, box = wordmark(110)
    width = max(256, box.width() + 40)
    sx = (width - 256) / 2
    tx, ty = (width - box.width()) / 2 - box.left(), 256 + 36 - box.top()
    svg("quotaring-stacked", f"0 0 {width:.0f} {ty + box.bottom() + 20:.0f}",
        f'<path fill="{MAIN}" transform="translate({sx:.2f} 0)" d="{SYMBOL}"/>'
        f'<path fill="{INK}" transform="translate({tx:.2f} {ty:.2f})" d="{text}"/>')

    # App icon: night tile, accent-coloured mark nudged up-left to sit on the optical centre.
    tile = f'<rect width="256" height="256" rx="56" fill="{NIGHT}"/>'
    # One per accent colour (the app draws the chosen one); the plain name is the default.
    for accent, (_light, dark) in ACCENTS.items():
        suffix = "" if accent == "slate" else f"-{accent}"
        svg(f"quotaring-app-icon{suffix}", "0 0 256 256", tile +
            f'<path fill="{dark}" transform="translate(124 124) scale(0.74) translate(-128 -128)" d="{SYMBOL}"/>')
        svg(f"quotaring-app-icon{suffix}-small", "0 0 256 256", tile +
            f'<path fill="{dark}" transform="translate(124 124) scale(0.8) translate(-128 -128)" d="{SYMBOL_SMALL}"/>')
    print("written to", OUT)


if __name__ == "__main__":
    main()
