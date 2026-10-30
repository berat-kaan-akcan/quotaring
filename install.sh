#!/bin/sh
# Install the latest QuotaRing release on Linux (x86_64):
#   curl -fsSL https://raw.githubusercontent.com/berat-kaan-akcan/quotaring/main/install.sh | sh
# Debian / Ubuntu: the .deb through apt (sudo asks for your password). Other distributions, or
# QUOTARING_APPIMAGE=1: the AppImage in ~/.local/bin with a menu entry, no root needed.
# Every download is checked against the release's SHA256SUMS.txt. Either way the app updates
# itself afterwards (Settings > General > Check for updates).
set -eu
BASE=https://github.com/berat-kaan-akcan/quotaring/releases/latest/download

fail() { echo "quotaring: $*" >&2; exit 1; }
[ "$(uname -s)" = Linux ] || fail "this script is for Linux; on Windows see the README"
[ "$(uname -m)" = x86_64 ] || fail "only x86_64 builds are published; build from source (see the README)"
command -v curl >/dev/null || fail "curl is needed"
command -v sha256sum >/dev/null || fail "sha256sum is needed"

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
  SUDO=
  [ "$(id -u)" = 0 ] || SUDO=sudo
  $SUDO apt-get install -y "$TMP/quotaring_amd64.deb"
  echo "QuotaRing is installed: start it from the app menu, or run: quotaring"
else
  fetch quotaring-x86_64.AppImage
  BIN=${XDG_BIN_HOME:-$HOME/.local/bin}
  APPS=${XDG_DATA_HOME:-$HOME/.local/share}/applications
  mkdir -p "$BIN" "$APPS"
  install -m 755 "$TMP/quotaring-x86_64.AppImage" "$BIN/quotaring.AppImage"
  cat > "$APPS/quotaring.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=QuotaRing
Comment=Claude Code, Codex and Antigravity usage
Exec="$BIN/quotaring.AppImage"
Icon=utilities-system-monitor
Categories=Utility;
Terminal=false
EOF
  echo "QuotaRing is installed in $BIN/quotaring.AppImage and in the app menu."
  echo "If it does not start, your system needs FUSE 2 (e.g. sudo apt install libfuse2, sudo dnf install fuse-libs)."
fi
