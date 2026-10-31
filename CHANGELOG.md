# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Notifications: a custom warning level (any percentage from 1 to 100) next to the suggested
  ones, through *+ Custom* in Settings.

## [0.2.0] - 2026-10-30

First public release.

### Added
- Tray icon drawn as a ring around the tightest current limit with its number, turning amber and
  red as it runs out: a thick ring with a gap around large pixel-drawn digits at the small tray
  sizes. Windows 11 shows it next to the clock on first run instead of under the overflow arrow;
  hiding it again in Windows settings is respected.
- Popup by the tray icon, also when it opens by itself (first start, a click on a notification).
  It stays where it opened while its page changes size, grows with its page up to 660 px (or the
  screen's height), and taller pages scroll under a fixed header. KDE Plasma Wayland: a
  layer-shell surface anchored by the panel; XWayland fallback elsewhere (`--xwayland`).
- Claude Code: 5-hour and weekly limits (plus per-model weekly caps) via the `claude` CLI's
  experimental `get_usage` control request; local token counts from `~/.claude/projects`.
- OpenAI Codex: ChatGPT-plan limits via `codex app-server`; local token counts from rollout logs.
- Google Antigravity: while it runs, the limits of its *View Usage* groups from its local language
  server (Linux and Windows), with the IDE's account-status cache as the fallback. Each model has
  its own row; the selected (or tightest) model shows its group's 5-hour limit on the outer ring
  and the weekly one on the inner ring. Local token counts from its conversation databases
  (read-only).
- Provider cards in two columns, rearranged by dragging; the order is saved.
- Tokens page: period and provider chips, total with what it would cost at API list prices
  (cache included), input / output / cache split, daily columns labelled with their values, and
  every model with its provider, cost and token split. Model ids read as names ("Gemini 3.8
  Flash", "Opus 5.5").
- API prices update themselves: LiteLLM's public price list at most once a week, OpenRouter's
  model list for models it lacks, and a built-in table for the rest (*Update API prices* in
  Settings).
- Notifications: warning levels of your choice, limit full, limit reset (off by default), per
  provider, with a test button; the tray menu turns them off or mutes them for an hour or until
  tomorrow. They say what is left and when it comes back, carry the limit's ring as their icon,
  and clicking one opens the popup.
- Settings as a page of the popup: theme, accent colour, language (English / Turkish), percent
  left or used, start at login, notifications, one line per provider with Track and Limits
  switches, and refresh intervals, timeout and command paths under *Advanced*.
- Updates: a newer GitHub release shows a banner in the popup and an item in the tray menu.
  *Update* downloads it, checks it against the release's SHA256SUMS.txt, installs it and starts
  the new version: through the Windows installer, by swapping the folder of the Windows zip or
  Linux tarball, by replacing the AppImage, or through apt under pkexec for the .deb. The Arch
  package and source checkouts get a link to the release page. The downloaded installer is
  removed once the new version runs. GitHub is asked at most twice a day; *Check for updates* in
  Settings turns it off.
- One-line installs: `curl -fsSL …/install.sh | sh` on Linux (the .deb through apt on
  Debian/Ubuntu, else the AppImage in ~/.local/bin with a menu entry) and
  `irm …/install.ps1 | iex` on Windows; both check the release's SHA256SUMS.txt.
- Packages with fixed file names, so the README's links always fetch the newest version: Linux
  tarball, `.deb` and AppImage (built on Ubuntu 22.04), Arch `PKGBUILD`, Windows per-user
  installer and zip.

[Unreleased]: https://github.com/berat-kaan-akcan/quotaring/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/berat-kaan-akcan/quotaring/releases/tag/v0.2.0
