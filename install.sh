#!/bin/sh
# Install the latest QuotaRing release on Linux (x86_64) and start it:
#   curl -fsSL https://raw.githubusercontent.com/berat-kaan-akcan/quotaring/main/install.sh | sh
# Debian / Ubuntu: the .deb through apt. Arch / CachyOS / Manjaro: the pacman package, which runs
# on the system's Qt, so on KDE Wayland the popup is anchored by the panel (layer-shell-qt).
# Other distributions, or QUOTARING_APPIMAGE=1: the AppImage in ~/.local/bin with a menu entry
# and a `quotaring` command. Python and Qt come inside the package (the Arch package gets them from
# pacman). sudo asks for your password where a system package is installed, and whatever is missing
# is added:
#   curl;  AppImage: FUSE 2, the graphics libraries and fonts;
#   Arch: a font if there is none;  KDE on Arch: layer-shell-qt;  GNOME: the AppIndicator extension, without which it has no tray.
# QUOTARING_TRAY_ONLY=1 only sets up GNOME's tray extension; the app's own banner offers this.
# Every QuotaRing download is checked against the release's SHA256SUMS.txt; the GNOME extension's
# fallback comes over HTTPS from extensions.gnome.org, as GNOME's own Extensions app would get it,
# where the zip differs per GNOME version and has no checksum to pin. The .deb, the AppImage and the Arch
# package (from 0.3.2) update themselves afterwards.
# QUOTARING_NO_DEPS=1 skips installing system packages, QUOTARING_NO_START=1 skips starting the app.
set -eu
BASE=https://github.com/berat-kaan-akcan/quotaring/releases/latest/download

fail() { echo "quotaring: $*" >&2; exit 1; }
say() { echo "quotaring: $*"; }
[ "$(uname -s)" = Linux ] || fail "this script is for Linux; on Windows see the README"
[ "$(uname -m)" = x86_64 ] || fail "only x86_64 builds are published; build from source (see the README)"
command -v sha256sum >/dev/null || fail "sha256sum is needed"

SUDO=
if [ "$(id -u)" != 0 ]; then
  SUDO=sudo
  command -v sudo >/dev/null || ! command -v pkexec >/dev/null || SUDO=pkexec
fi

# An old package list asks for files the mirror no longer has, so refresh it, once.
apt_refresh() {
  [ -n "${APT_FRESH:-}" ] && return 0
  APT_FRESH=1
  $SUDO apt-get update -qq || say "could not refresh the package list; trying with the one here"
}

# Install distribution packages: pkg_install <apt names> <dnf names> <pacman names> <zypper names>
pkg_install() {
  if command -v apt-get >/dev/null; then apt_refresh; $SUDO apt-get install -y $1
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

# Ubuntu's desktop can come without curl, and this script can be piped in from wget.
ensure_curl() {
  command -v curl >/dev/null && return 0
  say "installing curl, to download QuotaRing"
  { [ "${QUOTARING_NO_DEPS:-}" != 1 ] && pkg_install curl curl curl curl; } || fail "curl is needed"
}

ensure_fuse2() {
  has_lib libfuse.so.2 && return 0
  say "installing FUSE 2, which AppImages need to run"
  if [ "${QUOTARING_NO_DEPS:-}" = 1 ] || ! {
      if command -v apt-get >/dev/null; then
        apt_refresh
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

has_fonts() {
  [ -n "$(find /usr/share/fonts /usr/local/share/fonts -type f \( -name '*.ttf' -o -name '*.otf' \) 2>/dev/null | head -1)" ]
}

# What the AppImage leaves to the system: without these it does not start, or shows no text.
ensure_appimage_libs() {
  has_lib libGL.so.1 && has_lib libEGL.so.1 && has_lib libwayland-client.so.0 &&
    has_lib libfontconfig.so.1 && has_fonts && return 0
  say "installing the graphics libraries and fonts QuotaRing needs"
  if [ "${QUOTARING_NO_DEPS:-}" = 1 ] || ! pkg_install \
      "libgl1 libegl1 libwayland-client0 fontconfig fonts-dejavu-core" \
      "mesa-libGL mesa-libEGL libwayland-client fontconfig dejavu-sans-fonts" \
      "libglvnd mesa wayland fontconfig ttf-dejavu" \
      "Mesa-libGL1 Mesa-libEGL1 libwayland-client0 fontconfig dejavu-fonts"; then
    say "could not install them; if QuotaRing does not start, add OpenGL, EGL and fonts from your distribution"
  fi
}

# The extension that shows tray icons on GNOME, under the UUID Ubuntu ships it with and upstream's.
TRAY_EXTENSIONS="ubuntu-appindicators@ubuntu.com appindicatorsupport@rgcjonas.gmail.com"

# The tray extension on this system, whether or not the running shell has loaded it.
tray_extension() {
  KNOWN=$(gnome-extensions list 2>/dev/null || true)
  for EXT in $TRAY_EXTENSIONS; do
    printf '%s\n' "$KNOWN" | grep -qx "$EXT" && { echo "$EXT"; return 0; }
    for DIR in "${XDG_DATA_HOME:-$HOME/.local/share}" $(echo "${XDG_DATA_DIRS:-/usr/local/share:/usr/share}" | tr : ' '); do
      [ -d "$DIR/gnome-shell/extensions/$EXT" ] && { echo "$EXT"; return 0; }
    done
  done
  return 0
}

# For an extension the running shell has not loaded, which `gnome-extensions enable` refuses.
enable_at_next_login() {
  CURRENT=$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null) || return 0
  case "$CURRENT" in
    *"'$1'"*) return 0 ;;
    "@as []"|"[]") NEW="['$1']" ;;
    *) NEW="${CURRENT%]}, '$1']" ;;
  esac
  gsettings set org.gnome.shell enabled-extensions "$NEW" 2>/dev/null || true
}

# For systems with no package of it (openSUSE). Goes to the user's own extensions, so no sudo.
tray_from_gnome_org() {
  VERSION=$(gnome-shell --version 2>/dev/null | sed -n 's/[^0-9]*\([0-9][0-9]*\).*/\1/p')
  [ -n "$VERSION" ] || return 1
  INFO="https://extensions.gnome.org/extension-info/?uuid=appindicatorsupport@rgcjonas.gmail.com&shell_version=$VERSION"
  URL=$(curl -fsSL --proto =https "$INFO" | sed -n 's/.*"download_url": *"\([^"]*\)".*/\1/p') || return 1
  # Only this extension's own path: the value is glued onto the host, so it must not be able to change it.
  case "$URL" in
    "/download-extension/appindicatorsupport@rgcjonas.gmail.com.shell-extension.zip?version_tag="*) ;;
    *) return 1 ;;
  esac
  curl -fsSL --proto =https --retry 3 --retry-all-errors -o "$TMP/tray-extension.zip" "https://extensions.gnome.org$URL" || return 1
  gnome-extensions install --force "$TMP/tray-extension.zip" 2>/dev/null
}

ensure_gnome_tray() {
  case "${XDG_CURRENT_DESKTOP:-}" in *GNOME*) ;; *) return 0 ;; esac
  command -v gnome-extensions >/dev/null || return 0
  ENABLED=$(gnome-extensions list --enabled 2>/dev/null || true)
  for EXT in $TRAY_EXTENSIONS; do
    printf '%s\n' "$ENABLED" | grep -qx "$EXT" && return 0
  done
  EXT=$(tray_extension)
  if [ -z "$EXT" ]; then
    say "installing the AppIndicator extension, which GNOME needs to show tray icons"
    if [ "${QUOTARING_NO_DEPS:-}" = 1 ] || ! { pkg_install gnome-shell-extension-appindicator \
        gnome-shell-extension-appindicator gnome-shell-extension-appindicator \
        gnome-shell-extension-appindicator || tray_from_gnome_org; }; then
      say "could not install it; see https://extensions.gnome.org/extension/615/appindicator-support/"
      return 0
    fi
    EXT=$(tray_extension)
    [ -n "$EXT" ] || return 0
  fi
  gnome-extensions enable "$EXT" 2>/dev/null && return 0
  enable_at_next_login "$EXT"
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

# QuotaRing reads limits through these. They are the user's own tools and need their sign-in, so
# they are pointed out rather than installed.
point_out_tools() {
  { command -v claude || command -v codex || command -v agy ||
    ls -d "$HOME/.local/bin/claude" "$HOME"/.gemini/antigravity*; } >/dev/null 2>&1 && return 0
  say "no Claude Code, Codex or Antigravity found, so there are no limits to show yet."
  say "  Install and sign in to the ones you use, and the ring appears:"
  say "  Claude Code: curl -fsSL https://claude.ai/install.sh | bash   then run: claude"
  say "  Codex:       npm install -g @openai/codex   then run: codex login"
  say "  Antigravity: Google's app; sign in inside it"
}

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
chmod 755 "$TMP"  # apt reads the .deb as its own user

if [ "${QUOTARING_TRAY_ONLY:-}" = 1 ]; then
  ensure_gnome_tray
  say "done; if the icon is not there yet, log out and back in"
  exit 0
fi
ensure_curl
curl -fsSL --retry 3 --retry-all-errors -o "$TMP/SHA256SUMS.txt" "$BASE/SHA256SUMS.txt"
fetch() {
  echo "Downloading $1"
  curl -fL --retry 3 --retry-all-errors --progress-bar -o "$TMP/$1" "$BASE/$1"
  (cd "$TMP" && grep " \*\{0,1\}$1\$" SHA256SUMS.txt | sha256sum -c --quiet -) || fail "checksum mismatch for $1"
}

if [ "${QUOTARING_APPIMAGE:-}" != 1 ] && command -v apt-get >/dev/null && command -v dpkg >/dev/null; then
  fetch quotaring_amd64.deb
  chmod 644 "$TMP/quotaring_amd64.deb"
  apt_refresh
  $SUDO apt-get install -y "$TMP/quotaring_amd64.deb"  # pulls in its own dependencies
  ensure_gnome_tray
  say "installed: start it from the app menu, or run: quotaring"
  remove_appimage /opt/quotaring/quotaring
  start_app /opt/quotaring/quotaring
elif [ "${QUOTARING_APPIMAGE:-}" != 1 ] && command -v pacman >/dev/null; then
  fetch quotaring-any.pkg.tar.zst
  # pacman installs the dependencies (python, pyside6) from the repositories.
  $SUDO pacman -U --noconfirm "$TMP/quotaring-any.pkg.tar.zst" ||
    fail "pacman could not install it. If it could not fetch a dependency, run: sudo pacman -Syu, then this command again"
  # pyside6 brings no font; without one the popup has no text.
  has_fonts || [ "${QUOTARING_NO_DEPS:-}" = 1 ] || $SUDO pacman -S --needed --noconfirm ttf-dejavu ||
    say "could not install a font; add one if the popup shows no text"
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
  ensure_appimage_libs
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
point_out_tools
