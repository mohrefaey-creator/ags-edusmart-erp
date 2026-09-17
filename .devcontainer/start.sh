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
  || { echo "[start] compose up failed; see: docker compose ps"; exit 0; }

# Pull whatever landed on main since the last start, so a codespace created
# before a fix existed picks it up on its next wake. Scripts only — the site
# and its data are on volumes and untouched.
git pull -q origin main 2>/dev/null || true

# Wait for web, then make sure the setup wizard is done. The guard is inside
# complete-setup.sh, so on every start after the first this is one query and a
# "nothing to do".
for _ in $(seq 1 30); do
  h=$(docker compose -f compose.yaml -f compose.local.yaml ps web --format '{{.Health}}' 2>/dev/null | head -1)
  [ "${h}" = healthy ] && break
  sleep 10
done
bash complete-setup.sh 2>&1 | tail -4 || true
