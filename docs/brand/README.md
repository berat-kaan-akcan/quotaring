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
| `quotaring-app-icon.svg`, `-small.svg` (`-ink`, `-amber` variants) | App icon tile (the PNG/ICO files in `packaging/icons` are drawn from the same geometry by `quotaring.app.make_icon`) |
| `*-black.svg`, `*-white.svg` | One-colour versions for print, stamps, single-colour UI |

Rebuild everything with `QT_QPA_PLATFORM=offscreen python docs/brand/build_logo.py`, then
`python packaging/make_icons.py` for the app icons.

## Colour

QuotaRing has three accent colours; the user picks one in **Settings → Accent colour**, and the
app's accent and its icon follow it. **Slate** is the default and the colour of the logo files.

| Accent | On light | On dark | Character |
|---|---|---|---|
| Slate (default) | `#3F5468` | `#A9B8C8` | Calm, technical; reads almost neutral at tray size |
| Ink | `#1D1C1A` | `#ECEBE8` | The app's own text colour; sits in the tray like a system icon |
| Amber | `#A15F00` | `#F2B544` | Warm, gauge-like, bright on dark panels; the app's "limit near" colour moves to orange with it |

Neutrals: Night `#18191C` (app icon tile, dark backgrounds), Ink `#1D1C1A` (wordmark on light),
Paper `#F6F5F2` (light backgrounds).

None of the accents is close to the provider colours used inside the app (orange, green, blue);
those belong to the providers and are never used for the QuotaRing logo. Every accent passes
4.5:1 against its background (Slate 7.8:1 on white and 8.7:1 on Night; Amber 5.1:1 on white
and 9.6:1 on Night).

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
- Mix accents (a Slate ring with an Amber wordmark) or place an accent on mid-tone or busy backgrounds; use the white or black version instead.
