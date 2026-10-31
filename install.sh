#!/bin/sh
# Install the latest QuotaRing release on Linux (x86_64) and start it:
#   curl -fsSL https://raw.githubusercontent.com/berat-kaan-akcan/quotaring/main/install.sh | sh
# Debian / Ubuntu: the .deb through apt. Arch / CachyOS / Manjaro: the pacman package, which runs
# on the system's Qt, so on KDE Wayland the popup is anchored by the panel (layer-shell-qt).
# Other distributions, or QUOTARING_APPIMAGE=1: the AppImage in ~/.local/bin with a menu entry
# and a `quotaring` command. sudo asks for your password where a system package is installed:
#   AppImage: FUSE 2 (fuse2 / fuse-libs / libfuse2), which AppImages need to run;
#   KDE on Arch: layer-shell-qt;  GNOME: the AppIndicator extension, without which it has no tray.
# Every download is checked against the release's SHA256SUMS.txt. The .deb and the AppImage update
# themselves afterwards; run this command again to update the Arch package.
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

# A running copy: the .deb's and the AppImage's process is named quotaring; the Arch package's is
# Python running from /usr/share/quotaring.
stop_app() {
  PKG='^/usr/bin/python3 -c import sys; sys[.]path[.]insert[(]0, "/usr/share/quotaring"[)]'
  pkill -x quotaring 2>/dev/null || true
  pkill -f "$PKG" 2>/dev/null || true
  i=0
  while { pgrep -x quotaring || pgrep -f "$PKG"; } >/dev/null 2>&1 && [ $i -lt 50 ]; do
    sleep 0.1; i=$((i + 1))
  done
}

# An earlier AppImage install would shadow the package's menu entry and command: remove it.
remove_appimage() {
  BIN=${XDG_BIN_HOME:-$HOME/.local/bin}
  APPS=${XDG_DATA_HOME:-$HOME/.local/share}/applications
  [ -e "$BIN/quotaring.AppImage" ] || return 0
  say "removing the earlier AppImage install from $BIN"
  stop_app
  rm -f "$BIN/quotaring.AppImage"
  [ -L "$BIN/quotaring" ] && rm -f "$BIN/quotaring"
  grep -qs "quotaring.AppImage" "$APPS/quotaring.desktop" && rm -f "$APPS/quotaring.desktop"
  AUTO=${XDG_CONFIG_HOME:-$HOME/.config}/autostart/quotaring.desktop
  if grep -qs "quotaring.AppImage" "$AUTO"; then  # Start at login stays on, for the new install
    sed -i -e "s|^Exec=.*|Exec=$1|" -e "/^Path=/d" "$AUTO"
  fi
  rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps/quotaring.png"
}

# Start the installed app detached from this terminal, replacing a running copy (an update).
start_app() {
  [ "${QUOTARING_NO_START:-}" = 1 ] && return 0
  if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    say "no graphical session here; start it from the app menu"
    return 0
  fi
  stop_app
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
  remove_appimage /opt/quotaring/quotaring
  start_app /opt/quotaring/quotaring
elif [ "${QUOTARING_APPIMAGE:-}" != 1 ] && command -v pacman >/dev/null; then
  fetch quotaring-any.pkg.tar.zst
  # pacman installs the dependencies (python, pyside6) from the repositories.
  $SUDO pacman -U --noconfirm "$TMP/quotaring-any.pkg.tar.zst"
  case "${XDG_CURRENT_DESKTOP:-}" in *KDE*)
    # Lets the popup open anchored by the panel on Wayland; without it XWayland places it.
    [ "${QUOTARING_NO_DEPS:-}" = 1 ] || $SUDO pacman -S --needed --noconfirm --asdeps layer-shell-qt ||
      say "could not install layer-shell-qt; the popup opens through XWayland" ;;
  esac
  ensure_gnome_tray
  remove_appimage /usr/bin/quotaring
  say "installed: start it from the app menu, or run: quotaring"
  start_app /usr/bin/quotaring
else
  fetch quotaring-x86_64.AppImage
  ensure_fuse2
  ensure_gnome_tray
  BIN=${XDG_BIN_HOME:-$HOME/.local/bin}
  APPS=${XDG_DATA_HOME:-$HOME/.local/share}/applications
  mkdir -p "$BIN" "$APPS"
  chmod 755 "$TMP/quotaring-x86_64.AppImage"
  install -m 755 "$TMP/quotaring-x86_64.AppImage" "$BIN/quotaring.AppImage"
  ln -sf "$BIN/quotaring.AppImage" "$BIN/quotaring"
  # The logo for the menu entry and the taskbar, from the AppImage itself (no FUSE needed for that).
  ICON=utilities-system-monitor
  ICONS=${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps
  if (cd "$TMP" && ./quotaring-x86_64.AppImage --appimage-extract quotaring.png >/dev/null 2>&1) &&
      [ -s "$TMP/squashfs-root/quotaring.png" ]; then
    mkdir -p "$ICONS" && install -m 644 "$TMP/squashfs-root/quotaring.png" "$ICONS/quotaring.png" && ICON=quotaring
  fi
  cat > "$APPS/quotaring.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=QuotaRing
Comment=Claude Code, Codex and Antigravity usage
Exec="$BIN/quotaring.AppImage"
Icon=$ICON
Categories=Utility;
Terminal=false
StartupWMClass=quotaring
EOF
  command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
  say "installed in $BIN/quotaring.AppImage, in the app menu, and as the command: quotaring"
  start_app "$BIN/quotaring.AppImage"
fi
