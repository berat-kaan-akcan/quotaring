#!/usr/bin/env bash
# Build an AppImage from the Ubuntu 22.04 portable tarball, entirely inside a container:
# appimagetool is downloaded and run there, never on the host. NOT RUN by the automated
# session (its permission system refused running downloaded code) — run it yourself.
#   ./packaging/linux/build_in_docker.sh && ./packaging/linux/build_appimage_docker.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
VERSION=$(python3 -c "import re;print(re.search(r'__version__ = \"(.+)\"', open('aiusage/__init__.py').read())[1])")
TARBALL=packaging/out/ai-usage-widget-$VERSION-linux-x86_64-ubuntu22.04.tar.gz
[ -f "$TARBALL" ] || { echo "missing $TARBALL — run build_in_docker.sh first"; exit 1; }
TOOL_URL=${APPIMAGETOOL_URL:-https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage}
docker run --rm -v "$PWD":/src:ro -v "$PWD/packaging/out":/out -e VERSION="$VERSION" -e TOOL_URL="$TOOL_URL" \
  -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" ubuntu:22.04 bash -euc '
  export DEBIAN_FRONTEND=noninteractive
  apt-get -o Acquire::ForceIPv4=true update -qq >/dev/null
  apt-get -o Acquire::ForceIPv4=true install -y -qq curl file >/dev/null
  curl -4 -fsSL -o /tmp/appimagetool "$TOOL_URL"
  chmod +x /tmp/appimagetool
  echo "appimagetool sha256: $(sha256sum /tmp/appimagetool | cut -d" " -f1)"
  A=/tmp/AppDir; mkdir -p $A/usr/bin
  tar -xzf /out/ai-usage-widget-$VERSION-linux-x86_64-ubuntu22.04.tar.gz -C /tmp
  cp -a /tmp/ai-usage-widget/. $A/usr/bin/
  install -m644 /src/packaging/linux/ai-usage-widget.desktop $A/
  install -m644 /src/packaging/icons/ai-usage-widget-256.png $A/ai-usage-widget.png
  printf "#!/bin/sh\nexec \"\$(dirname \"\$(readlink -f \"\$0\")\")/usr/bin/ai-usage-widget\" \"\$@\"\n" > $A/AppRun
  chmod +x $A/AppRun
  F=/out/ai-usage-widget-$VERSION-x86_64.AppImage
  ARCH=x86_64 /tmp/appimagetool --appimage-extract-and-run --no-appstream $A "$F" >/tmp/ait.log 2>&1 || { tail -20 /tmp/ait.log; exit 1; }
  chown "$HOST_UID:$HOST_GID" "$F"
  file "$F"
  echo "built packaging/out/$(basename "$F")"
'
