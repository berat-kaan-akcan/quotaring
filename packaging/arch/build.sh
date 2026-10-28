#!/usr/bin/env bash
# Create the source tarball from the committed tree and build the Arch package.
# Pass --nodeps to build without pyside6 installed (the package still depends on it).
set -euo pipefail
cd "$(dirname "$0")"
VER=$(sed -n 's/^pkgver=//p' PKGBUILD)
git -C ../.. archive --format=tar.gz --prefix="ai-usage-widget-$VER/" -o "$PWD/ai-usage-widget-$VER.tar.gz" HEAD
makepkg -f "$@"
mkdir -p ../out && mv -f ai-usage-widget-*.pkg.tar.* ../out/
