#!/usr/bin/env bash
# Build the PyInstaller bundle and the Linux packages this machine has tools for.
#   ./packaging/linux/build_linux.sh            -> tarball + .deb (+ AppImage if appimagetool exists)
# Output: packaging/out/
# For broad glibc compatibility, build on the OLDEST distro you target (e.g. Ubuntu 22.04).
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT=$PWD
VERSION=$(python3 -c "import re;print(re.search(r'__version__ = \"(.+)\"', open('aiusage/__init__.py').read())[1])")
ARCH=$(uname -m)
OUT=$ROOT/packaging/out
PY=${PYTHON:-$ROOT/.venv/bin/python}
mkdir -p "$OUT"

"$PY" -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/aiusage.spec

# 1) portable tarball
tar -C dist -czf "$OUT/ai-usage-widget-$VERSION-linux-$ARCH.tar.gz" ai-usage-widget
echo "built $OUT/ai-usage-widget-$VERSION-linux-$ARCH.tar.gz"

# Shared filesystem layout: /opt/ai-usage-widget + launcher + desktop file + icons
stage() {
  local dest=$1
  mkdir -p "$dest/opt" "$dest/usr/bin" "$dest/usr/share/applications"
  cp -a dist/ai-usage-widget "$dest/opt/ai-usage-widget"
  ln -sf /opt/ai-usage-widget/ai-usage-widget "$dest/usr/bin/ai-usage-widget"
  install -m644 packaging/linux/ai-usage-widget.desktop "$dest/usr/share/applications/"
  for s in 16 32 48 64 128 256; do
    install -Dm644 "packaging/icons/ai-usage-widget-$s.png" \
      "$dest/usr/share/icons/hicolor/${s}x${s}/apps/ai-usage-widget.png"
  done
}

# 2) .deb (dpkg-deb if available, otherwise assembled with ar + tar, which is the same format)
DEBARCH=$([ "$ARCH" = x86_64 ] && echo amd64 || echo "$ARCH")
DEB=$(mktemp -d)
stage "$DEB/root"
mkdir -p "$DEB/root/DEBIAN"
cat > "$DEB/root/DEBIAN/control" <<CTRL
Package: ai-usage-widget
Version: $VERSION
Section: utils
Priority: optional
Architecture: $DEBARCH
Maintainer: AI Usage Widget maintainers <noreply@example.invalid>
Description: Desktop widget for Claude Code, Codex and Antigravity usage
 Shows local token activity and provider-reported account quota.
CTRL
DEBFILE="$OUT/ai-usage-widget_${VERSION}_${DEBARCH}.deb"
if command -v dpkg-deb >/dev/null; then
  dpkg-deb --root-owner-group --build "$DEB/root" "$DEBFILE"
else
  (cd "$DEB/root" && tar --owner=0 --group=0 -czf "$DEB/control.tar.gz" -C DEBIAN .)
  (cd "$DEB/root" && tar --owner=0 --group=0 --exclude=./DEBIAN -czf "$DEB/data.tar.gz" .)
  echo "2.0" > "$DEB/debian-binary"
  rm -f "$DEBFILE"
  (cd "$DEB" && ar rc "$DEBFILE" debian-binary control.tar.gz data.tar.gz)
fi
rm -rf "$DEB"
echo "built $DEBFILE"

# 3) AppImage (needs appimagetool on PATH; not downloaded automatically)
if command -v appimagetool >/dev/null; then
  APPDIR=$(mktemp -d)/AppDir
  mkdir -p "$APPDIR/usr/bin"
  cp -a dist/ai-usage-widget/. "$APPDIR/usr/bin/"
  install -m644 packaging/linux/ai-usage-widget.desktop "$APPDIR/"
  install -m644 packaging/icons/ai-usage-widget-256.png "$APPDIR/ai-usage-widget.png"
  printf '#!/bin/sh\nexec "$(dirname "$(readlink -f "$0")")/usr/bin/ai-usage-widget" "$@"\n' > "$APPDIR/AppRun"
  chmod +x "$APPDIR/AppRun"
  ARCH=$ARCH appimagetool "$APPDIR" "$OUT/ai-usage-widget-$VERSION-$ARCH.AppImage"
  echo "built $OUT/ai-usage-widget-$VERSION-$ARCH.AppImage"
else
  echo "appimagetool not found: AppImage NOT built (see README)"
fi
