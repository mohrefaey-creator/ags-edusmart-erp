#!/usr/bin/env bash
# Do N logins as the same user at once and report what comes back.
#
#   sudo bash scripts/probe-login-concurrency.sh [count] [parallel]
#
# Sequential logins for one user succeed (probe-auth.sh proves that), yet the
# school-day profile crosses its login-failure threshold with hundreds of VUs
# signing in as the same three accounts. The difference between those two facts
# is concurrency, and this is the smallest thing that reproduces it.
set -uo pipefail

BENCH_DIR=${BENCH_DIR:-/home/frappe/frappe-bench}
BENCH_USER=${BENCH_USER:-frappe}
SITE=${SITE:-ags.localhost}
PORT=${PORT:-8013}
USER_ID=${USER_ID:-lt.teacher@loadtest.invalid}
PASSWORD=${PASSWORD:-loadtest-not-real}
COUNT=${1:-60}
PARALLEL=${2:-30}

if [ "$(id -u)" -eq 0 ] && id -u "${BENCH_USER}" >/dev/null 2>&1; then
  exec su - "${BENCH_USER}" -c \
    "BENCH_DIR='${BENCH_DIR}' SITE='${SITE}' PORT='${PORT}' USER_ID='${USER_ID}' \
     PASSWORD='${PASSWORD}' bash '${BASH_SOURCE[0]}' '${COUNT}' '${PARALLEL}'"
fi

cd "${BENCH_DIR}/sites" || exit 1
"${BENCH_DIR}/env/bin/gunicorn" --bind "0.0.0.0:${PORT}" --workers 4 --preload \
  --access-logfile /dev/null frappe.app:application > /tmp/ags-probe-login.log 2>&1 &
PID=$!
OUT=$(mktemp -d)
trap 'kill "${PID}" 2>/dev/null; rm -rf "${OUT}"' EXIT

BASE="http://${SITE}:${PORT}"
RESOLVE="${SITE}:${PORT}:127.0.0.1"
for _ in $(seq 1 40); do
  curl -sf -m 5 --resolve "${RESOLVE}" "${BASE}/api/method/ping" >/dev/null 2>&1 && break
  sleep 2
done

export BASE RESOLVE USER_ID PASSWORD OUT
one() {
  curl -s -m 30 --resolve "${RESOLVE}" \
    -d "usr=${USER_ID}" -d "pwd=${PASSWORD}" \
    -o "${OUT}/body.$1" -w '%{http_code}' "${BASE}/api/method/login" > "${OUT}/code.$1"
}
export -f one

echo "firing ${COUNT} logins as ${USER_ID}, ${PARALLEL} at a time"
seq 1 "${COUNT}" | xargs -P "${PARALLEL}" -I{} bash -c 'one {}'

echo
echo "status codes:"
cat "${OUT}"/code.* | sort | uniq -c | sed 's/^/  /'

echo
echo "distinct non-200 bodies:"
grep -l . "${OUT}"/body.* 2>/dev/null | while read -r f; do
  n=${f##*.}
  [ "$(cat "${OUT}/code.${n}" 2>/dev/null)" = "200" ] && continue
  head -c 300 "${f}" | tr -d '\n'
  echo
done | sort -u | head -5 | sed 's/^/  /'
