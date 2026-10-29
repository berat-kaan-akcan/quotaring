#!/usr/bin/env bash
# Build the PyInstaller bundle and the Linux packages this machine has tools for.
#   ./packaging/linux/build_linux.sh            -> tarball + .deb (+ AppImage if appimagetool exists)
# Output: packaging/out/
# For broad glibc compatibility, build on the OLDEST distro you target (e.g. Ubuntu 22.04).
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT=$PWD
VERSION=$(python3 -c "import re;print(re.search(r'__version__ = \"(.+)\"', open('quotaring/__init__.py').read())[1])")
ARCH=$(uname -m)
OUT=$ROOT/packaging/out
PY=${PYTHON:-$ROOT/.venv/bin/python}
mkdir -p "$OUT"

"$PY" -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/quotaring.spec

# 1) portable tarball
tar -C dist -czf "$OUT/quotaring-$VERSION-linux-$ARCH.tar.gz" quotaring
echo "built $OUT/quotaring-$VERSION-linux-$ARCH.tar.gz"

# 2) .deb
"$ROOT/packaging/linux/make_deb.sh" dist/quotaring "$OUT" "$VERSION"

# 3) AppImage (needs appimagetool on PATH; not downloaded automatically)
if command -v appimagetool >/dev/null; then
  APPDIR=$(mktemp -d)/AppDir
  mkdir -p "$APPDIR/usr/bin"
  cp -a dist/quotaring/. "$APPDIR/usr/bin/"
  install -m644 packaging/linux/quotaring.desktop "$APPDIR/"
  install -m644 packaging/icons/quotaring-256.png "$APPDIR/quotaring.png"
  printf '#!/bin/sh\nexec "$(dirname "$(readlink -f "$0")")/usr/bin/quotaring" "$@"\n' > "$APPDIR/AppRun"
  chmod +x "$APPDIR/AppRun"
  ARCH=$ARCH appimagetool "$APPDIR" "$OUT/quotaring-$VERSION-$ARCH.AppImage"
  echo "built $OUT/quotaring-$VERSION-$ARCH.AppImage"
else
  echo "appimagetool not found: AppImage NOT built (see README)"
fi
