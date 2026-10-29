# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
- Settings: theme, language (English / Turkish, follows the system by default), percent left or
  used, refresh intervals, start at login, quota notifications, per-provider toggles, CLI paths.
- KDE Plasma Wayland: popup as a layer-shell surface anchored by the panel; XWayland fallback
  elsewhere (`--xwayland`).
- Packages: Linux tarball, `.deb` and AppImage (built on Ubuntu 22.04), Arch `PKGBUILD`,
  Windows per-user installer and zip.

[Unreleased]: https://github.com/berat-kaan-akcan/quotaring/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/berat-kaan-akcan/quotaring/releases/tag/v0.1.0
