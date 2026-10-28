# AI Usage Widget

A small always-visible desktop widget that shows **Claude Code**, **OpenAI Codex** and
**Google Antigravity** usage in one place. One Python + Qt (PySide6) codebase for Windows and
Linux (GNOME / KDE, X11 / Wayland).

Each provider card has two clearly separated parts:

| Section | What it is | Where it comes from |
|---|---|---|
| **Account quota** | Percent of a subscription limit used, plus reset time | Reported by the provider's own CLI (see below). Never computed locally. |
| **Local activity · recorded tokens** | Tokens recorded in local logs: today, last 5 h, last 7 d (expanded view: per model, 30 d, all) | Local history files, read-only |

Local token counts are **not** quota. The widget never derives remaining quota from local history.
If a value can't be retrieved, the card says so: *Unavailable*, *Not authenticated*,
*Not installed*, *Unsupported*, *Rate limited*, or *Stale (last updated …)*.

## What is supported

| Provider | Local activity | Account quota |
|---|---|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` (exact counts per API response, deduplicated) | 5-hour and weekly limits (plus per-model weekly caps and the weekly share of Claude Code / claude.ai Chats / Cowork) via the `claude` CLI's `get_usage` control request. **Experimental and undocumented**; may break with a Claude Code update. Verified with Claude Code 2.1.312. |
| Codex | `~/.codex/sessions` and `archived_sessions` rollout logs | ChatGPT-plan limits via `codex app-server` → `account/rateLimits/read` (documented). API-key accounts show *Unsupported*; API billing is never shown as plan quota. **Not tested on a real Codex install** (none on the dev machine). |
| Antigravity | `~/.gemini/antigravity{,-ide,-cli}/conversations/*.db` — token counts stored per model response (undocumented internal format, opened read-only) | *Unavailable*: no documented or credential-free source exists. |

The weekly Claude limit is account-wide: it includes claude.ai web/desktop chats, as the
"weekly share" line shows. Local Claude Code logs do **not** contain claude.ai conversations.
Details and evidence: [RESEARCH.md](RESEARCH.md).

## Install

### From source (any OS)
Requires Python 3.10+.

```sh
git clone <this repo> ai-usage-widget && cd ai-usage-widget
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt         # Windows: .venv\Scripts\pip ...
.venv/bin/python -m aiusage                       # Windows: .venv\Scripts\pythonw -m aiusage
```

### Linux packages
Recommended: `./packaging/linux/build_in_docker.sh` builds inside Ubuntu 22.04 (glibc 2.35, runs the
tests there first) and produces a bundle that runs on Ubuntu 22.04+, Debian 12+, Fedora, Arch, …:
- Portable: extract `ai-usage-widget-<ver>-linux-x86_64-ubuntu22.04.tar.gz`, run `ai-usage-widget/ai-usage-widget`.
- Debian/Ubuntu: `sudo apt install ./ai-usage-widget_<ver>~ubuntu22.04_amd64.deb` (installs to `/opt`).

`./packaging/linux/build_linux.sh` does the same on the host without Docker (the result only runs
on distros at least as new as the build machine).
- Arch/CachyOS: `./packaging/arch/build.sh -s` then `sudo pacman -U packaging/out/ai-usage-widget-*.pkg.tar.zst`
  (uses system `python` + `pyside6`).
- AppImage: `./packaging/linux/build_appimage_docker.sh` (downloads and runs appimagetool inside a container).

Frozen builds bundle the build machine's libraries; build on the **oldest** distro you
target (e.g. Ubuntu 22.04) so the result runs on newer ones.

### Windows
In PowerShell from the repo root: `powershell -ExecutionPolicy Bypass -File packaging\windows\build_windows.ps1`.
This runs the tests, builds `dist\ai-usage-widget\ai-usage-widget.exe`, a zip, and — if
[Inno Setup 6](https://jrsoftware.org/isinfo.php) is installed — a per-user installer
(`packaging\out\ai-usage-widget-<ver>-setup.exe`, no admin rights needed).

## Use

- **Drag** the header to move; **resize** from the bottom-right grip.
- ⟳ refresh now · ▾ expanded view (per-model table + period picker, quota source, weekly share)
  · ⚙ settings · ✕ hide to tray (or quit, if tray is disabled/unavailable).
- Tray icon: click to show/hide; right-click for Refresh, Settings, Quit.
- Hover the token numbers for input / output / reasoning / cache breakdown; the expanded view
  also has a 14-day bar chart of locally recorded tokens (hover a bar for the day's total).
- Right-click anywhere in the widget for the same menu as the tray (useful on GNOME without a tray).
- Keys: F5 / Ctrl+R refresh · Ctrl+E expand · Ctrl+, settings · Esc hide · Ctrl+Q quit.
- The tray tooltip summarizes each provider (quota only when the provider reported it).
- Only one instance runs per user; a second launch exits (`--allow-multiple` overrides).

Command line: `--hidden` (start in tray), `--xwayland` (see Wayland below), `--debug`
(verbose logs), `--print` (collect once and print JSON, no window), `--version`.

## Settings

Saved as JSON in:
- Linux: `$XDG_CONFIG_HOME/ai-usage-widget/settings.json` (default `~/.config/...`)
- Windows: `%APPDATA%\AIUsageWidget\settings.json`

Language: follows the system (Turkish or English); override in Settings → Language
(takes effect after a restart).

Options: local refresh interval (default 60 s), quota refresh interval (default 300 s), query
timeout (20 s), theme (system / light / dark), background opacity, keep above other windows,
close-to-tray, start at login, quota notification threshold (default 90 %, only for fresh,
provider-reported values), per-provider enable and quota toggles, custom `claude` / `codex` paths.

Cache (last good results, incremental-scan state): `$XDG_CACHE_HOME/ai-usage-widget/`
or `%LOCALAPPDATA%\AIUsageWidget\Cache\`. It holds model names, token counts, message ids and
history file paths — no conversation text. Delete it any time; it is rebuilt.

## Start at login

Toggle **Start at login** in Settings.
- Linux: writes `~/.config/autostart/ai-usage-widget.desktop` (XDG autostart; works on GNOME and KDE).
- Windows: writes `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\AIUsageWidget`
  (the installer's "Start at login" task writes the same value).

## Privacy and security

- Provider files are only **read**: JSONL files in binary read mode, SQLite with `mode=ro`.
- The widget **never reads, stores or logs credentials**. Quota is obtained by starting the
  provider's own CLI, which uses its own login:
  - `claude --safe-mode --print --input-format stream-json --output-format stream-json
    --no-session-persistence --permission-mode dontAsk --tools ""` in an empty temp folder, sending
    only the `initialize` and `get_usage` control requests (no model turn, no tools, no hooks).
  - `codex app-server`, sending `initialize`, `account/read` (without token refresh) and
    `account/rateLimits/read`.
  The CLIs' stderr is discarded. Every query has a timeout and at most 3 attempts with backoff;
  rate limiting (HTTP 429) backs the quota check off to at least 15 minutes.
- Logs contain paths and error types only. `--debug` adds tracebacks.

## Platform notes and limitations

- **Wayland:** compositors decide window placement. Saved position and "keep above" are
  usually ignored for native Wayland clients (GNOME ignores them; KDE may too). Dragging works
  everywhere (uses `startSystemMove`). Options: start with `--xwayland` (keep-above and
  position should then work on KDE and GNOME — not verified here), or on KDE add
  a KWin window rule ("Keep above") for `ai-usage-widget`.
- **GNOME tray:** GNOME has no tray by default. Install/enable the *AppIndicator and
  KStatusNotifierItem Support* extension, or turn off "close hides to tray" so ✕ quits.
  Without a tray the window stays visible.
- **Opacity** is applied to the window background (works with any compositor); text stays opaque.
- A harmless `qt.qpa.services: Failed to register with host portal` warning appears when running
  from source without an installed `.desktop` file.
- PySide6 6.12 aborts at exit on Python < 3.12 (a reference-counting bug in its bindings);
  `requirements.txt` therefore selects PySide6 < 6.12 on those Python versions.
- Antigravity's database format is internal and may change; unreadable data is skipped and the
  count of skipped databases is shown.
- Claude's `get_usage` is experimental; a CLI update can turn it into *Unsupported* or *Unavailable*.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Claude/Codex quota "Not installed" but the CLI is installed | Set its full path in Settings (GUI sessions may not have `~/.local/bin` on `PATH`). |
| Quota "Not authenticated" | Run `claude` or `codex login` once in a terminal. |
| Quota "Unsupported" | API-key account (no subscription limits) or a CLI version without the query. |
| Numbers look old | Hover "updated …"; press ⟳. A *Stale* label means the last refresh failed and old values are shown. |
| Want to inspect raw output | `python -m aiusage --print` |
| "already running" but no window | It is in the tray (or right-click menu → Show). A lock left by a crashed run is taken over automatically. |
| `claude` installed with the native installer but "Not installed" | The widget also looks in `~/.local/share/claude/versions/`; otherwise set the path in Settings. |

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q          # synthetic fixtures only; never reads your real data
```

Layout: `aiusage/model.py` (data types), `aiusage/providers/` (one module per provider behind
`providers/base.py`), `aiusage/engine.py` (caching, stale handling, scheduling),
`aiusage/ui/` (Qt widgets), `packaging/` (PyInstaller spec, Linux/Arch/Windows packaging).

## Credits

Ideas and protocol knowledge (deduplication strategy, Codex cumulative counters, CLI-based quota
queries) come from two MIT-licensed projects:
[yusufipk/kde-agents-usage](https://github.com/yusufipk/kde-agents-usage) and
[RanulfoMNeto/agent-usage](https://github.com/RanulfoMNeto/agent-usage). No code was copied.

License: MIT.
