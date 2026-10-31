#!/bin/sh
# Install the latest QuotaRing release on Linux (x86_64) and start it:
#   curl -fsSL https://raw.githubusercontent.com/berat-kaan-akcan/quotaring/main/install.sh | sh
# Debian / Ubuntu: the .deb through apt (sudo asks for your password). Other distributions, or
# QUOTARING_APPIMAGE=1: the AppImage in ~/.local/bin with a menu entry and a `quotaring` command.
# Missing system packages are installed with your package manager (sudo asks for your password):
#   AppImage: FUSE 2 (fuse2 / fuse-libs / libfuse2), which AppImages need to run;
#   GNOME:    the AppIndicator extension, without which GNOME has no tray.
# Every download is checked against the release's SHA256SUMS.txt. Either way the app updates
# itself afterwards (Settings > General > Check for updates).
# QUOTARING_NO_DEPS=1 skips installing system packages, QUOTARING_NO_START=1 skips starting the app.
set -eu
BASE=https://github.com/berat-kaan-akcan/quotaring/releases/latest/download

fail() { echo "quotaring: $*" >&2; exit 1; }
say() { echo "quotaring: $*"; }
[ "$(uname -s)" = Linux ] || fail "this script is for Linux; on Windows see the README"
[ "$(uname -m)" = x86_64 ] || fail "only x86_64 builds are published; build from source (see the README)"
command -v curl >/dev/null || fail "curl is needed"
command -v sha256sum >/dev/null || fail "sha256sum is needed"

SUDO=
[ "$(id -u)" = 0 ] || SUDO=sudo

# Install distribution packages: pkg_install <apt names> <dnf names> <pacman names> <zypper names>
pkg_install() {
  if command -v apt-get >/dev/null; then $SUDO apt-get install -y $1
  elif command -v dnf >/dev/null; then $SUDO dnf install -y $2
  elif command -v pacman >/dev/null; then $SUDO pacman -S --needed --noconfirm $3
  elif command -v zypper >/dev/null; then $SUDO zypper --non-interactive install $4
  else return 1
  fi
}

has_lib() {
  { command -v ldconfig >/dev/null && ldconfig -p 2>/dev/null | grep -q "$1"; } ||
    ls /usr/lib/"$1"* /usr/lib64/"$1"* /usr/lib/x86_64-linux-gnu/"$1"* /lib/x86_64-linux-gnu/"$1"* >/dev/null 2>&1
}

ensure_fuse2() {
  has_lib libfuse.so.2 && return 0
  say "installing FUSE 2, which AppImages need to run"
  if [ "${QUOTARING_NO_DEPS:-}" = 1 ] || ! {
      if command -v apt-get >/dev/null; then
        # Ubuntu 24.04+ renamed it libfuse2t64.
        $SUDO apt-get install -y libfuse2t64 2>/dev/null || $SUDO apt-get install -y libfuse2
      else
        pkg_install libfuse2 fuse-libs fuse2 libfuse2
      fi
    }; then
    say "could not install FUSE 2; install it yourself:"
    say "  Arch/CachyOS: sudo pacman -S fuse2   Fedora: sudo dnf install fuse-libs"
    say "  Ubuntu 24.04+: sudo apt install libfuse2t64   openSUSE: sudo zypper install libfuse2"
  fi
}

ensure_gnome_tray() {
  case "${XDG_CURRENT_DESKTOP:-}" in *GNOME*) ;; *) return 0 ;; esac
  command -v gnome-extensions >/dev/null || return 0
  EXT=appindicatorsupport@rgcjonas.gmail.com
  gnome-extensions list --enabled 2>/dev/null | grep -qx "$EXT" && return 0
  if ! gnome-extensions list 2>/dev/null | grep -qx "$EXT"; then
    say "installing the AppIndicator extension, which GNOME needs to show tray icons"
    if [ "${QUOTARING_NO_DEPS:-}" = 1 ] || ! pkg_install gnome-shell-extension-appindicator \
        gnome-shell-extension-appindicator gnome-shell-extension-appindicator \
        gnome-shell-extension-appindicator; then
      say "could not install it; see https://extensions.gnome.org/extension/615/appindicator-support/"
      return 0
    fi
  fi
  gnome-extensions enable "$EXT" 2>/dev/null || true
  say "GNOME loads a new extension after you log out and back in; until then QuotaRing opens as a window"
}

# Start the installed app detached from this terminal, replacing a running copy (an update).
start_app() {
  [ "${QUOTARING_NO_START:-}" = 1 ] && return 0
  if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    say "no graphical session here; start it from the app menu"
    return 0
  fi
  # The app's process is named quotaring both from the .deb and inside the AppImage.
  if pkill -x quotaring 2>/dev/null; then
    i=0
    while pgrep -x quotaring >/dev/null 2>&1 && [ $i -lt 50 ]; do sleep 0.1; i=$((i + 1)); done
  fi
  if command -v setsid >/dev/null; then
    setsid -f "$1" >/dev/null 2>&1 </dev/null
  else
    nohup "$1" >/dev/null 2>&1 </dev/null &
  fi
  say "QuotaRing is running: look for its icon in the system tray"
}

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
chmod 755 "$TMP"  # apt reads the .deb as its own user

curl -fsSL -o "$TMP/SHA256SUMS.txt" "$BASE/SHA256SUMS.txt"
fetch() {
  echo "Downloading $1"
  curl -fL --progress-bar -o "$TMP/$1" "$BASE/$1"
  (cd "$TMP" && grep " \*\{0,1\}$1\$" SHA256SUMS.txt | sha256sum -c --quiet -) || fail "checksum mismatch for $1"
}

if [ "${QUOTARING_APPIMAGE:-}" != 1 ] && command -v apt-get >/dev/null && command -v dpkg >/dev/null; then
  fetch quotaring_amd64.deb
  chmod 644 "$TMP/quotaring_amd64.deb"
  $SUDO apt-get install -y "$TMP/quotaring_amd64.deb"  # pulls in its own dependencies
  ensure_gnome_tray
  say "installed: start it from the app menu, or run: quotaring"
  start_app /opt/quotaring/quotaring
else
  fetch quotaring-x86_64.AppImage
  ensure_fuse2
  ensure_gnome_tray
  BIN=${XDG_BIN_HOME:-$HOME/.local/bin}
  APPS=${XDG_DATA_HOME:-$HOME/.local/share}/applications
  mkdir -p "$BIN" "$APPS"
  install -m 755 "$TMP/quotaring-x86_64.AppImage" "$BIN/quotaring.AppImage"
  ln -sf "$BIN/quotaring.AppImage" "$BIN/quotaring"
  cat > "$APPS/quotaring.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=QuotaRing
Comment=Claude Code, Codex and Antigravity usage
Exec="$BIN/quotaring.AppImage"
Icon=utilities-system-monitor
Categories=Utility;
Terminal=false
StartupWMClass=quotaring
EOF
  command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
  say "installed in $BIN/quotaring.AppImage, in the app menu, and as the command: quotaring"
  start_app "$BIN/quotaring.AppImage"
fi
