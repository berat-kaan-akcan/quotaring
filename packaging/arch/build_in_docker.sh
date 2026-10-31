#!/usr/bin/env bash
# Build the Arch package (any arch: Python sources on the system's Python + PySide6) inside an
# archlinux container, from the committed tree. Output: packaging/out/quotaring-<ver>-<rel>-any.pkg.tar.zst
#   ./packaging/arch/build_in_docker.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p packaging/out
SRC=$(mktemp -d)
trap 'rm -rf "$SRC"' EXIT
git archive --format=tar HEAD | tar -x -C "$SRC"
docker run --rm -v "$SRC":/src:ro -v "$PWD/packaging/out":/out \
  -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" archlinux:latest bash -euc '
  pacman -Syu --noconfirm --needed base-devel python git >/dev/null
  useradd -m builder
  cp -r /src /home/builder/quotaring
  chown -R builder: /home/builder/quotaring
  cd /home/builder/quotaring
  # build.sh archives HEAD, so give the copy a commit of its own.
  su builder -c "git init -q && git add -A && git -c user.name=build -c user.email=build@localhost commit -qm build \
    && ./packaging/arch/build.sh --nodeps >/dev/null"
  install -o "$HOST_UID" -g "$HOST_GID" -m644 packaging/out/quotaring-*-any.pkg.tar.* /out/
  ls packaging/out/
'
