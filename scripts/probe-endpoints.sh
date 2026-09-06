#!/usr/bin/env bash
# Hit every endpoint the school-day profile uses, as each cohort's user, and
# print the status code.
#
#   sudo bash scripts/probe-endpoints.sh
#
# k6 reports "83% failed" without saying which request or why. A load profile
# whose requests are 403 measures the permission denial path at a few
# milliseconds and calls it fast — so this is the first thing to run whenever
# the failure rate is high but the latencies look implausibly good.
set -uo pipefail

BENCH_DIR=${BENCH_DIR:-/home/frappe/frappe-bench}
BENCH_USER=${BENCH_USER:-frappe}
SITE=${SITE:-ags.localhost}
PORT=${PORT:-8012}
LOADTEST_PASSWORD=${LOADTEST_PASSWORD:-loadtest-not-real}

if [ "$(id -u)" -eq 0 ] && id -u "${BENCH_USER}" >/dev/null 2>&1; then
  exec su - "${BENCH_USER}" -c \
    "BENCH_DIR='${BENCH_DIR}' SITE='${SITE}' PORT='${PORT}' \
     LOADTEST_PASSWORD='${LOADTEST_PASSWORD}' bash '${BASH_SOURCE[0]}'"
fi

cd "${BENCH_DIR}/sites" || exit 1
"${BENCH_DIR}/env/bin/gunicorn" --bind "0.0.0.0:${PORT}" --workers 2 --preload \
  --access-logfile /dev/null frappe.app:application > /tmp/ags-probe-ep.log 2>&1 &
PID=$!
JAR=$(mktemp)
trap 'kill "${PID}" 2>/dev/null; rm -f "${JAR}"' EXIT

BASE="http://${SITE}:${PORT}"
RESOLVE="${SITE}:${PORT}:127.0.0.1"
for _ in $(seq 1 40); do
  curl -sf -m 5 --resolve "${RESOLVE}" "${BASE}/api/method/ping" >/dev/null 2>&1 && break
  sleep 2
done

# name|path, matching load-tests/k6/school-day.js
ENDPOINTS='student_groups|/api/method/frappe.client.get_list?doctype=Student%20Group&limit_page_length=20
class_roster|/api/method/frappe.client.get_list?doctype=Student&limit_page_length=40
attendance_count|/api/method/frappe.client.get_count?doctype=Student%20Attendance
invoice_list|/api/method/frappe.client.get_list?doctype=Sales%20Invoice&limit_page_length=20
collection_cases|/api/method/frappe.client.get_list?doctype=AGS%20Collection%20Case&limit_page_length=20
purchase_requests|/api/method/frappe.client.get_list?doctype=Material%20Request&limit_page_length=20
payer_account|/api/method/frappe.client.get_list?doctype=AGS%20Payer%20Account&limit_page_length=5
kpi_read|/api/method/ags_edusmart.ags_dashboards.kpi_engine.read'

for user in lt.parent001@loadtest.invalid lt.teacher001@loadtest.invalid lt.staff001@loadtest.invalid; do
  : > "${JAR}"
  code=$(curl -s -m 10 --resolve "${RESOLVE}" -c "${JAR}" \
    -d "usr=${user}" -d "pwd=${LOADTEST_PASSWORD}" \
    -o /dev/null -w '%{http_code}' "${BASE}/api/method/login")
  printf '\n== %s  (login %s)\n' "${user}" "${code}"
  if [ "${code}" != "200" ]; then
    echo "   login failed — every request below would be unauthenticated"
  fi

  while IFS='|' read -r name path; do
    [ -n "${name}" ] || continue
    status=$(curl -s -m 20 --resolve "${RESOLVE}" -b "${JAR}" \
      -o /tmp/ags-probe-body -w '%{http_code}' "${BASE}${path}")
    note=""
    if [ "${status}" != "200" ]; then
      note=$(head -c 200 /tmp/ags-probe-body | tr -d '\n' | sed 's/[[:space:]]\+/ /g')
    fi
    printf '   %-18s %s  %s\n' "${name}" "${status}" "${note}"
  done <<< "${ENDPOINTS}"
done
