# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Provider cards can be rearranged: drag a card from anywhere on it to where you want it
  (with a mouse, or a touchpad's double-tap-and-drag); the order is saved.
- Tokens page (click the token strip): period and provider chips, total with what it would cost
  at API list prices (cache included), input / output / cache split, daily columns labelled with
  their values, and every model with its provider, cost and token split.
- API prices update themselves: LiteLLM's public price list is downloaded at most once a week
  and cached, OpenRouter's model list fills in models it lacks (Gemini 4 Argon), and a built-in
  table covers the rest. *Update API prices* in Settings turns
  it off.
- Notification settings of their own: several warning levels, limit full, limit reset (off by
  default), per provider, and a test button; the tray menu turns them off or mutes them for an
  hour or until tomorrow. Older single-threshold settings carry over.
- Windows 11: the tray icon is shown next to the clock on first run instead of under the
  overflow arrow; hiding it again in Windows settings is respected.
- Larger, sharper tray number: a thinner ring and pixel-drawn digits at the small tray sizes
  instead of a blurred font.

### Fixed
- The same quota notification no longer repeats on every poll: providers report the reset time
  with a little jitter, and each new value counted as a new limit window.
- The provider card order is now really restored after a restart.
- Hovering a ring showed an empty box instead of its tooltip. Tooltips now each have their own
  instance and use the popup's colours.

### Changed
- Notifications say what is left and when it comes back: "Claude Code · Weekly limit: 9% left",
  "91% used · resets Mon 00:23 (3d 4h)"; "Claude Code · 5-hour limit reached", "Resets in 2h 12m."
  Their icon is the limit as a ring with what is left, amber or red; clicking one opens the popup.
- The popup header carries the QuotaRing mark next to the name, in the accent colour.
- Settings are a page of the popup (gear icon, or *Settings…* in the tray menu) instead of a
  separate window.
- The popup grows with its page up to 660 px (or the screen's height); taller pages scroll
  under a fixed header.
- Settings are shorter: one line per provider with Track and Limits switches, and refresh
  intervals, timeout and command paths under a collapsed *Advanced* section.
- Antigravity: while Antigravity runs, limits come from its local language server — the same
  groups as its "View Usage" panel (Gemini, Claude and GPT: 5 hours and weekly; Gemini 4 Argon:
  weekly). Each model keeps its own row; the selected (or tightest) model shows its group's
  5-hour limit on the outer ring and the weekly one on the inner ring. The IDE's account-status
  cache stays as the fallback. Per-model rows no longer carry initials.
- Antigravity's rings: hovering one shows its limit in the middle and fades the other, as on
  the other cards; the middle names the limit ("5 hours", "Weekly") and the model sits under
  the rings. GPT model ids read as "GPT-5.5" like the other models.
- Model names: Antigravity's variant ids ("gemini-3.8-flash-n", "claude-opus-5-5-medium") are
  shown as one model ("Gemini 3.8 Flash", "Opus 5.5").

## [0.1.0] - 2026-10-29

First public release.

### Added
- Tray icon drawn as a ring around the tightest current limit; click opens a popup by the panel.
- Claude Code: 5-hour and weekly limits (plus per-model weekly caps) via the `claude` CLI's
  experimental `get_usage` control request; local token counts from `~/.claude/projects`.
- OpenAI Codex: ChatGPT-plan limits via `codex app-server`; local token counts from rollout logs.
- Google Antigravity: per-model limits from the IDE's local account-status cache; local token
  counts from its conversation databases (read-only).
- Token strip: today, 7 days and a 7-day bar chart from local history, for all providers or
  one picked from the chips above it.
- Settings: theme, accent colour (Slate, Ink, Amber; the app icon follows it), language (English / Turkish, follows the system by default), percent left or
  used, refresh intervals, start at login, quota notifications, per-provider toggles, CLI paths.
- KDE Plasma Wayland: popup as a layer-shell surface anchored by the panel; XWayland fallback
  elsewhere (`--xwayland`).
- Packages: Linux tarball, `.deb` and AppImage (built on Ubuntu 22.04), Arch `PKGBUILD`,
  Windows per-user installer and zip.

[Unreleased]: https://github.com/berat-kaan-akcan/quotaring/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/berat-kaan-akcan/quotaring/releases/tag/v0.1.0
