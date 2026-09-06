#!/usr/bin/env bash
# Install the k6 load generator.
#
# Fetches the release binary rather than adding an apt repository: one binary,
# no key management, and the version is pinned in one visible place.
#
#   sudo bash scripts/install-k6.sh [version]
set -euo pipefail

VERSION=${1:-}

if command -v k6 >/dev/null 2>&1 && [ -z "${VERSION}" ]; then
  echo "k6 already installed: $(k6 version)"
  exit 0
fi

if [ -z "${VERSION}" ]; then
  VERSION=$(curl -fsSL https://api.github.com/repos/grafana/k6/releases/latest \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')
fi

ARCH=$(uname -m)
case "${ARCH}" in
  x86_64)  ARCH=amd64 ;;
  aarch64) ARCH=arm64 ;;
  *) echo "unsupported architecture: ${ARCH}" >&2; exit 1 ;;
esac

PKG="k6-${VERSION}-linux-${ARCH}"
URL="https://github.com/grafana/k6/releases/download/${VERSION}/${PKG}.tar.gz"

echo "installing ${PKG}"
WORK=$(mktemp -d)
trap 'rm -rf "${WORK}"' EXIT

curl -fsSL "${URL}" -o "${WORK}/k6.tar.gz" \
  || { echo "download failed: ${URL}" >&2; exit 1; }
tar xzf "${WORK}/k6.tar.gz" -C "${WORK}"
install -m 0755 "${WORK}/${PKG}/k6" /usr/local/bin/k6

k6 version
