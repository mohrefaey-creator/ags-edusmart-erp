#!/usr/bin/env bash
# Is Caddy actually terminating TLS and reaching the web tier?
#
#   sudo bash scripts/compose-tls-probe.sh
#
# Separates the three things a failed HTTPS check can mean: Caddy has no
# certificate, Caddy has one but cannot reach the app, or the probe itself is
# wrong. Asked from inside the caddy container, so nothing depends on the host's
# port forwarding or name resolution.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}/deploy/compose" || exit 1
SITE=$(grep -E '^SITE_NAME=' .env | cut -d= -f2)
echo "site: ${SITE}"

echo
echo "=== does caddy have a certificate ==="
docker compose exec -T caddy sh -c \
  'ls -R /data/caddy/certificates 2>/dev/null | head -20 || echo "no certificates directory"'

echo
echo "=== caddy log, last 20 ==="
docker compose logs --tail=20 --no-log-prefix caddy 2>&1 | tail -20

echo
echo "=== plain HTTP to caddy (should redirect) ==="
docker compose exec -T caddy sh -c \
  "wget -S -qO- --header='Host: ${SITE}' http://localhost/api/method/ping 2>&1 | head -6"

echo
echo "=== HTTPS to caddy ==="
docker compose exec -T caddy sh -c \
  "wget -S -qO- --no-check-certificate --header='Host: ${SITE}' https://localhost/api/method/ping 2>&1 | head -12"

echo
echo "=== can caddy reach the web container at all ==="
docker compose exec -T caddy sh -c \
  "wget -qO- --header='Host: ${SITE}' http://web:8000/api/method/ping 2>&1 | head -3"
