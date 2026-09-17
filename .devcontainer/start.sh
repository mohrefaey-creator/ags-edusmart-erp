#!/usr/bin/env bash
# Runs on every codespace start, including after it has slept. Brings the
# containers back; the site, its database and the image all survive sleep on
# the codespace's disk, so this is fast.
set -uo pipefail
cd "$(dirname "$0")/../deploy/compose" || exit 1

# On first creation setup.sh has not run yet and there is no .env; do nothing.
[ -f .env ] || exit 0

for _ in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 2; done
docker compose -f compose.yaml -f compose.local.yaml up -d >/dev/null 2>&1 \
  && echo "[start] stack up — port 8080" \
  || echo "[start] compose up failed; see: docker compose ps"
