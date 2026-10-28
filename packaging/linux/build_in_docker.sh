#!/usr/bin/env bash
# Build the Linux bundle inside Ubuntu 22.04 (glibc 2.35) so it runs on 22.04 and newer distros.
# The source is mounted read-only; tests run in the container first.
#   ./packaging/linux/build_in_docker.sh     -> packaging/out/*-ubuntu22.04.tar.gz
set -euo pipefail
cd "$(dirname "$0")/../.."
# Prepared image (deps preinstalled) if present, else plain Ubuntu 22.04 (installs deps each run).
#   docker build -t aiusage-ubuntu2204 -f packaging/linux/Dockerfile.ubuntu2204 .
if [ -z "${IMAGE:-}" ]; then
  IMAGE=ubuntu:22.04
  docker image inspect aiusage-ubuntu2204 >/dev/null 2>&1 && IMAGE=aiusage-ubuntu2204
fi
mkdir -p packaging/out
docker run --rm -v "$PWD":/src:ro -v "$PWD/packaging/out":/out \
  -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 "$IMAGE" bash -euc '
  export DEBIAN_FRONTEND=noninteractive
  if [ -x /venv/bin/python ]; then ln -s /venv /tmp/venv; else
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv python3-pip libpython3.10 binutils dpkg-dev \
    libgl1 libegl1 libxkbcommon0 libxkbcommon-x11-0 libfontconfig1 libdbus-1-3 libglib2.0-0 \
    libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
    libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libwayland-client0 libwayland-cursor0 libwayland-egl1 >/dev/null
  python3 -m venv /tmp/venv
  /tmp/venv/bin/pip install -q --upgrade pip
  /tmp/venv/bin/pip install -q -r /src/requirements-dev.txt
  fi
  mkdir /tmp/w && cp -r /src/aiusage /src/packaging /src/tests /src/pytest.ini /tmp/w/
  rm -rf /tmp/w/packaging/out
  cd /tmp/w
  python3 --version
  QT_QPA_PLATFORM=offscreen /tmp/venv/bin/python -m pytest -q -p no:cacheprovider
  /tmp/venv/bin/python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/aiusage.spec >/tmp/pyi.log 2>&1 || { tail -30 /tmp/pyi.log; exit 1; }
  VERSION=$(/tmp/venv/bin/python -c "import aiusage;print(aiusage.__version__)")
  F=/out/ai-usage-widget-$VERSION-linux-x86_64-ubuntu22.04.tar.gz
  tar -C dist -czf "$F" ai-usage-widget
  QT_QPA_PLATFORM=offscreen dist/ai-usage-widget/ai-usage-widget --version
  echo "built packaging/out/$(basename "$F")"
  packaging/linux/make_deb.sh dist/ai-usage-widget /out "$VERSION" "~ubuntu22.04"
  chown "$HOST_UID:$HOST_GID" /out/*ubuntu22.04*
'
