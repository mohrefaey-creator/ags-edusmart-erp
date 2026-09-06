#!/usr/bin/env bash
# Run load-tests/k6/probe-session.js against a throwaway gunicorn.
#
#   sudo bash scripts/probe-session.sh [user]
#
# Answers "does k6 carry the session cookie" in about twenty seconds, instead of
# inferring it from an eight-minute profile's failure rate.
set -uo pipefail

BENCH_DIR=${BENCH_DIR:-/home/frappe/frappe-bench}
BENCH_USER=${BENCH_USER:-frappe}
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE=${SITE:-ags.localhost}
PORT=${PORT:-8014}
LOADTEST_PASSWORD=${LOADTEST_PASSWORD:-loadtest-not-real}
USER_ID=${1:-lt.staff001@loadtest.invalid}

if [ "$(id -u)" -eq 0 ] && id -u "${BENCH_USER}" >/dev/null 2>&1; then
  exec su - "${BENCH_USER}" -c \
    "BENCH_DIR='${BENCH_DIR}' SITE='${SITE}' PORT='${PORT}' \
     LOADTEST_PASSWORD='${LOADTEST_PASSWORD}' bash '${BASH_SOURCE[0]}' '${USER_ID}'"
fi

cd "${BENCH_DIR}/sites" || exit 1
"${BENCH_DIR}/env/bin/gunicorn" --bind "0.0.0.0:${PORT}" --workers 2 --preload \
  --access-logfile /dev/null frappe.app:application > /tmp/ags-probe-session.log 2>&1 &
PID=$!
trap 'kill "${PID}" 2>/dev/null' EXIT

for _ in $(seq 1 40); do
  curl -sf -m 5 --resolve "${SITE}:${PORT}:127.0.0.1" \
    "http://${SITE}:${PORT}/api/method/ping" >/dev/null 2>&1 && break
  sleep 2
done

cd "${REPO_ROOT}/load-tests/k6" || exit 1
k6 run --no-usage-report \
  -e "BASE_URL=http://${SITE}:${PORT}" \
  -e "SITE_HOST=${SITE}" \
  -e "USER=${USER_ID}" \
  -e "PASSWORD=${LOADTEST_PASSWORD}" \
  probe-session.js 2>&1 | grep -E "login |set-cookie|jar keys|follow-up|logged user"
