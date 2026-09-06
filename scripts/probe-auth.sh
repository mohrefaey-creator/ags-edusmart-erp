#!/usr/bin/env bash
# Answer one question before spending eight minutes on a load run:
# does a second login as the same user invalidate the first session?
#
# The unscaled school-day run failed 94% of its requests with every cohort
# signed in as Administrator. Session invalidation on re-login is the obvious
# suspect, but "obvious suspect" is not a diagnosis — this checks it.
set -uo pipefail

BENCH_DIR=${BENCH_DIR:-/home/frappe/frappe-bench}
BENCH_USER=${BENCH_USER:-frappe}
SITE=${SITE:-ags.localhost}
PORT=${PORT:-8011}
USER_ID=${USER_ID:-Administrator}
PASSWORD=${PASSWORD:-dev-admin-not-real}

if [ "$(id -u)" -eq 0 ] && id -u "${BENCH_USER}" >/dev/null 2>&1; then
  exec su - "${BENCH_USER}" -c \
    "BENCH_DIR='${BENCH_DIR}' SITE='${SITE}' PORT='${PORT}' \
     USER_ID='${USER_ID}' PASSWORD='${PASSWORD}' bash '${BASH_SOURCE[0]}'"
fi

echo "deny_multiple_sessions in site config:"
grep -o '"deny_multiple_sessions"[^,}]*' \
  "${BENCH_DIR}/sites/${SITE}/site_config.json" \
  "${BENCH_DIR}/sites/common_site_config.json" 2>/dev/null \
  || echo "  not set (Frappe default)"

cd "${BENCH_DIR}/sites" || exit 1
"${BENCH_DIR}/env/bin/gunicorn" --bind "0.0.0.0:${PORT}" --workers 2 --preload \
  --access-logfile /dev/null frappe.app:application > /tmp/ags-probe.log 2>&1 &
PID=$!
trap 'kill "${PID}" 2>/dev/null; wait "${PID}" 2>/dev/null' EXIT

BASE="http://${SITE}:${PORT}"
RESOLVE="${SITE}:${PORT}:127.0.0.1"
for _ in $(seq 1 40); do
  curl -sf -m 5 --resolve "${RESOLVE}" "${BASE}/api/method/ping" >/dev/null 2>&1 && break
  sleep 2
done

login() {  # $1 = cookie jar path
  curl -s -m 10 --resolve "${RESOLVE}" -c "$1" \
    -d "usr=${USER_ID}" -d "pwd=${PASSWORD}" \
    -o /dev/null -w '%{http_code}' "${BASE}/api/method/login"
}
probe() {  # $1 = cookie jar path
  curl -s -m 10 --resolve "${RESOLVE}" -b "$1" \
    -o /dev/null -w '%{http_code}' \
    "${BASE}/api/method/frappe.client.get_count?doctype=Student"
}

A=$(mktemp); B=$(mktemp)
trap 'rm -f "${A}" "${B}"; kill "${PID}" 2>/dev/null' EXIT

echo
echo "session A login          : $(login "${A}")"
echo "session A request        : $(probe "${A}")"
echo "session B login (same u) : $(login "${B}")"
echo "session A request again  : $(probe "${A}")   <- 403 here means re-login kills the first session"
echo "session B request        : $(probe "${B}")"

echo
echo "unauthenticated request  : $(curl -s -m 10 --resolve "${RESOLVE}" \
  -o /dev/null -w '%{http_code}' "${BASE}/api/method/frappe.client.get_count?doctype=Student")"
