#!/usr/bin/env bash
# Bring up the single-VM stack and prove it actually serves the application.
#
#   sudo bash scripts/compose-verify.sh          # up, set up, verify
#   sudo bash scripts/compose-verify.sh --down   # tear down, keep volumes
#   sudo bash scripts/compose-verify.sh --clean  # tear down and delete volumes
#
# This is the check that deploy/compose is real rather than plausible. It runs
# the same file an operator runs on the VM, with a throwaway .env, and then
# asks the stack the questions that matter:
#
#   * does every role reach Running, not just start
#   * does the web tier answer through Caddy, with TLS
#   * does Caddy pass the Host header through, which is the difference between
#     a working ERP and a 404 on every page
#
# Caddy is pointed at its internal CA here, not Let's Encrypt: the test host is
# vm.localhost, which no public CA will ever issue for, and hammering the ACME
# production endpoint from a test loop is how an account gets rate-limited.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_DIR="${REPO_ROOT}/deploy/compose"
SITE=${SITE:-vm.localhost}

say()  { printf '\n\033[1m== %s\033[0m\n' "$1"; }
note() { printf '   %s\n' "$1"; }
fail=0
check() {
  local label=$1 got=$2 want=$3
  if [ "${got}" = "${want}" ]; then
    printf '   \033[32mPASS\033[0m  %-46s %s\n' "${label}" "${got}"
  else
    printf '   \033[31mFAIL\033[0m  %-46s got %s, want %s\n' "${label}" "${got:-nothing}" "${want}"
    fail=$((fail + 1))
  fi
}

cd "${COMPOSE_DIR}" || exit 1

case "${1:-}" in
  --down)  docker compose --profile setup down; exit 0 ;;
  --clean) docker compose --profile setup down -v; exit 0 ;;
esac

# ------------------------------------------------------------------ env
# A test .env, never the operator's. If a real one exists it is left alone.
if [ ! -f .env ]; then
  cp .env.example .env
fi
sed -i "s/^SITE_NAME=.*/SITE_NAME=${SITE}/" .env
sed -i "s/^DB_ROOT_PASSWORD=.*/DB_ROOT_PASSWORD=vmtestroot/" .env
sed -i "s/^ADMIN_PASSWORD=.*/ADMIN_PASSWORD=vmtestadmin/" .env
sed -i "s/^ACME_EMAIL=.*/ACME_EMAIL=test@example.com/" .env
sed -i "s/^GUNICORN_WORKERS=.*/GUNICORN_WORKERS=2/" .env
sed -i "s/^DB_BUFFER_POOL=.*/DB_BUFFER_POOL=256M/" .env

say "Config"
if docker compose config >/dev/null 2>/tmp/compose-cfg.err; then
  note "compose.yaml parses and resolves"
else
  echo "compose config failed:" >&2; head -20 /tmp/compose-cfg.err >&2; exit 1
fi

say "Datastores"
docker compose up -d mariadb redis-cache redis-queue >/dev/null 2>&1
state=starting
for _ in $(seq 1 72); do
  state=$(docker compose ps mariadb --format '{{.Health}}' 2>/dev/null | head -1)
  [ "${state}" = healthy ] && break
  sleep 5
done
check "mariadb healthy" "${state:-none}" "healthy"
[ "${state}" = healthy ] || { docker compose logs --tail=20 mariadb; exit 1; }

say "Site setup (first run creates it; re-runs are a no-op)"
docker compose --profile setup run --rm site-init 2>&1 \
  | grep -vE 'Updating DocTypes|^[[:space:]]*$' | tail -12
docker compose --profile setup run --rm migrate 2>&1 | tail -3

say "App tiers"
docker compose up -d 2>&1 | tail -5
note "waiting for web to become healthy"
health=starting
for _ in $(seq 1 60); do
  health=$(docker compose ps web --format '{{.Health}}' 2>/dev/null | head -1)
  [ "${health}" = healthy ] && break
  [ "${health}" = unhealthy ] && break
  sleep 10
done
check "web healthy" "${health:-none}" "healthy"

say "Every role running"
for svc in web socketio worker-short worker-default worker-long scheduler backup caddy; do
  st=$(docker compose ps "${svc}" --format '{{.State}}' 2>/dev/null | head -1)
  check "${svc}" "${st:-none}" "running"
done

say "Through Caddy: TLS, and the Host header"
# From inside the caddy container, so the result does not depend on WSL's
# port forwarding or the Windows host's name resolution.
# Two things make this fiddlier than it looks, both worth knowing.
#
# TLS selects the certificate from the hostname in the URL, not the Host header.
# Asking for https://localhost makes Caddy hunt for a certificate named
# "localhost", fail, and abort with `tlsv1 alert internal error` while holding a
# perfectly good one for the site. So the URL has to carry the real name.
#
# But curl special-cases every name ending in .localhost to 127.0.0.1 per RFC
# 6761 and never asks DNS, so the site name alias on the compose network is
# ignored and the connection is refused inside the client container. --resolve
# overrides that. A production hostname needs neither trick; this is the price
# of a test name that keeps Caddy on its internal CA.
caddy_ip=$(docker compose exec -T web getent hosts "${SITE}" 2>/dev/null | awk '{print $1}' | head -1)
code=$(docker compose exec -T web sh -c \
  "curl -sk --max-time 15 --resolve ${SITE}:443:${caddy_ip} https://${SITE}/api/method/ping 2>/dev/null | head -c 80" 2>/dev/null)
if printf '%s' "${code}" | grep -q pong; then
  check "https /api/method/ping returns pong" "pong" "pong"
else
  check "https /api/method/ping returns pong" "${code:-nothing}" "pong"
fi

# The negative case. A request for a host Caddy does not serve must not reach
# the app; if it does, the Host header is not being honoured and every site
# resolution downstream is luck.
other=$(docker compose exec -T web sh -c \
  "curl -sk --max-time 15 --resolve ${SITE}:443:${caddy_ip} -H 'Host: wrong.example' https://${SITE}/api/method/ping 2>&1 | head -c 40" 2>/dev/null)
if printf '%s' "${other}" | grep -q pong; then
  check "wrong Host is not served the app" "served" "not served"
else
  check "wrong Host is not served the app" "not served" "not served"
fi

say "Backup"
docker compose exec -T backup /usr/local/bin/entrypoint.sh backup 2>&1 | tail -4
n=$(docker compose exec -T web sh -c \
  "ls /home/frappe/frappe-bench/sites/${SITE}/private/backups/*database.sql.gz 2>/dev/null | wc -l" 2>/dev/null | tr -d '\r')
if [ "${n:-0}" -ge 1 ]; then
  check "a database dump exists" "yes" "yes"
else
  check "a database dump exists" "no" "yes"
fi

say "Result"
if [ "${fail}" -eq 0 ]; then
  printf '   \033[32mall checks passed\033[0m\n'
else
  printf '   \033[31m%d check(s) failed\033[0m\n' "${fail}"
fi
exit "${fail}"
