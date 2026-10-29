# QuotaRing brand

<img src="quotaring-symbol.svg" width="96" alt="QuotaRing symbol">

**The idea:** a Q drawn as a gauge. The ring is three quarters full, like a quota in use, and the
tail is the needle. It is the app's tray ring turned into a letter.

## Files

| File | Use |
|---|---|
| `quotaring-horizontal.svg` | Default logo on light backgrounds (README, website header) |
| `quotaring-horizontal-dark.svg` | Same on dark backgrounds |
| `quotaring-stacked.svg` | Square-ish spaces (social preview, splash) |
| `quotaring-symbol.svg` | Symbol alone, 48 px and up |
| `quotaring-symbol-small.svg` | Heavier cut for 16–32 px (favicon, tray) |
| `quotaring-app-icon.svg`, `-small.svg` | App icon tile (the PNG/ICO files in `packaging/icons` are drawn from the same geometry by `quotaring.app.make_icon`) |
| `*-black.svg`, `*-white.svg` | One-colour versions for print, stamps, single-colour UI |

Rebuild everything with `QT_QPA_PLATFORM=offscreen python docs/brand/build_logo.py`, then
`python packaging/make_icons.py` for the app icons.

## Colour

| Name | HEX | RGB | Use |
|---|---|---|---|
| Ring Purple | `#9448D6` | 148, 72, 214 | Symbol on light backgrounds; the app's light-theme accent |
| Lilac | `#C99CF5` | 201, 156, 245 | Symbol on dark backgrounds; the app's dark-theme accent |
| Night | `#18191C` | 24, 25, 28 | App icon tile, dark backgrounds |
| Ink | `#1D1C1A` | 29, 28, 26 | Wordmark on light backgrounds |
| Paper | `#F6F5F2` | 246, 245, 242 | Light backgrounds |

**Why purple:** the app's provider rings sit at orange (~15°), green (~165°) and blue (~217°) on the
colour wheel. Purple (~272°) fills the largest free gap, so the logo and the app's accent never
clash with a provider ring yet sit calmly on the warm neutral backgrounds. The provider colours
belong to those providers and are never used for the QuotaRing logo.

Ring Purple on white has a contrast ratio of 5.1:1 (4.6:1 on Paper) and Lilac on Night 8.0:1,
all above the WCAG 3:1 minimum for graphics and 4.5:1 for text.

## Type

Wordmark: Noto Sans Bold (SIL Open Font License), converted to outlines, tracking −1 %.
Use Noto Sans for text set next to the logo.

## Clear space and size

- Keep a margin of at least the **ring's stroke width** (14 % of the symbol's height) on every side.
- Minimum sizes: symbol 16 px (use the small cut below 48 px); horizontal logo 96 px wide.

## Don't

- Recolour the symbol in provider colours or add gradients, shadows or outlines.
- Close the ring, move the gap or change the tail's angle; the open quarter is the idea.
- Stretch, rotate or set the wordmark in another typeface.
- Place Ring Purple on mid-tone or busy backgrounds; use the white or black version instead.
