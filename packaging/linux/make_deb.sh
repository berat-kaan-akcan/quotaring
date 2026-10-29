#!/usr/bin/env bash
# make_deb.sh <pyinstaller dist/quotaring dir> <output dir> <version> [suffix]
# Uses dpkg-deb when available, otherwise assembles the same ar/tar format by hand.
set -euo pipefail
SRC=$(cd "$1" && pwd); OUT=$2; VERSION=$3; SUFFIX=${4:-}
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../.." && pwd)
ARCH=$(uname -m); DEBARCH=$([ "$ARCH" = x86_64 ] && echo amd64 || echo "$ARCH")
DEB=$(mktemp -d)
R=$DEB/root
mkdir -p "$R/opt" "$R/usr/bin" "$R/usr/share/applications" "$R/DEBIAN"
cp -a "$SRC" "$R/opt/quotaring"
ln -sf /opt/quotaring/quotaring "$R/usr/bin/quotaring"
install -m644 "$HERE/quotaring.desktop" "$R/usr/share/applications/"
for s in 16 32 48 64 128 256; do
  install -Dm644 "$ROOT/packaging/icons/quotaring-$s.png" \
    "$R/usr/share/icons/hicolor/${s}x${s}/apps/quotaring.png"
done
cat > "$R/DEBIAN/control" <<CTRL
Package: quotaring
Version: $VERSION
Section: utils
Priority: optional
Architecture: $DEBARCH
Depends: libgl1, libegl1, libxkbcommon0, libfontconfig1, libdbus-1-3, libglib2.0-0
Maintainer: Berat Kaan Akcan <beratkaanakcan@gmail.com>
Description: Desktop widget for Claude Code, Codex and Antigravity usage
 Shows local token activity and provider-reported account quota.
CTRL
mkdir -p "$OUT"
F="$(cd "$OUT" && pwd)/quotaring_${VERSION}${SUFFIX}_${DEBARCH}.deb"
if command -v dpkg-deb >/dev/null; then
  dpkg-deb --root-owner-group --build "$R" "$F" >/dev/null
else
  (cd "$R" && tar --owner=0 --group=0 -czf "$DEB/control.tar.gz" -C DEBIAN .)
  (cd "$R" && tar --owner=0 --group=0 --exclude=./DEBIAN -czf "$DEB/data.tar.gz" .)
  echo "2.0" > "$DEB/debian-binary"
  rm -f "$F"
  (cd "$DEB" && ar rc "$F" debian-binary control.tar.gz data.tar.gz)
fi
rm -rf "$DEB"
echo "built $F"
