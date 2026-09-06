#!/usr/bin/env bash
# Run the load profiles against a production-shaped process model.
#
#   bash scripts/load-test.sh calibrate      # find per-worker throughput
#   bash scripts/load-test.sh school-day     # the full day profile
#   bash scripts/load-test.sh both
#
# Deliberately NOT run against `bench serve`. That is Werkzeug, single-process
# and single-threaded; measuring it tells you about Werkzeug, not about the
# system. This starts gunicorn with the same flags the container image uses, so
# the numbers extrapolate to the deployed topology.
#
# Worker count defaults to what this machine can actually hold rather than the
# 17 in the capacity model - a Frappe worker resides around 200-250 MB, so 17 of
# them need ~4 GB for the app tier alone. calibrate.js reports per-worker
# throughput precisely so a small run can be scaled up honestly.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BENCH_DIR=${BENCH_DIR:-/home/frappe/frappe-bench}
BENCH_USER=${BENCH_USER:-frappe}
SITE=${SITE:-ags.localhost}
PORT=${PORT:-8010}
WORKERS=${WORKERS:-4}
PEAK_RPS=${PEAK_RPS:-60}
ADMIN_PASSWORD=${ADMIN_PASSWORD:-dev-admin-not-real}
MODE=${1:-both}

if [ "$(id -u)" -eq 0 ] && id -u "${BENCH_USER}" >/dev/null 2>&1; then
  # ADMIN_PASSWORD must be forwarded too: without it the re-exec falls back to
  # the default and every k6 login fails, which reads as "the app is broken"
  # rather than "the harness dropped a variable".
  exec su - "${BENCH_USER}" -c \
    "BENCH_DIR='${BENCH_DIR}' SITE='${SITE}' PORT='${PORT}' WORKERS='${WORKERS}' \
     PEAK_RPS='${PEAK_RPS}' ADMIN_PASSWORD='${ADMIN_PASSWORD}' \
     bash '${BASH_SOURCE[0]}' '${MODE}'"
fi

say() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

command -v k6 >/dev/null 2>&1 || {
  echo "k6 not installed — run: sudo bash scripts/install-k6.sh" >&2; exit 1; }

GUNICORN_PID=""
cleanup() {
  if [ -n "${GUNICORN_PID}" ]; then
    kill "${GUNICORN_PID}" 2>/dev/null
    wait "${GUNICORN_PID}" 2>/dev/null
    echo "gunicorn stopped"
  fi
}
trap cleanup EXIT

say "Starting gunicorn (${WORKERS} workers) on :${PORT}"
cd "${BENCH_DIR}/sites" || { echo "no bench at ${BENCH_DIR}" >&2; exit 1; }

# Same flags as infra/docker/entrypoint.sh, so the measurement transfers.
"${BENCH_DIR}/env/bin/gunicorn" \
  --bind "0.0.0.0:${PORT}" \
  --workers "${WORKERS}" \
  --threads 1 \
  --worker-class sync \
  --timeout 120 \
  --graceful-timeout 30 \
  --max-requests 5000 \
  --max-requests-jitter 500 \
  --keep-alive 5 \
  --preload \
  --access-logfile /dev/null \
  --error-logfile - \
  frappe.app:application > /tmp/ags-gunicorn.log 2>&1 &
GUNICORN_PID=$!

# Reached by hostname, not by localhost.
#
# Frappe resolves the site from the request's Host header and falls back to
# common_site_config's default_site, which on this bench is a different site
# with none of the AGS tables. A request to http://localhost:PORT therefore
# reaches the wrong database and fails in a way that reads as "gunicorn did not
# come up". --resolve gives curl the right Host without touching /etc/hosts; k6
# gets the same effect from its `hosts` option.
PING="http://${SITE}:${PORT}/api/method/ping"
RESOLVE="${SITE}:${PORT}:127.0.0.1"

for _ in $(seq 1 60); do
  curl -sf -m 5 --resolve "${RESOLVE}" "${PING}" >/dev/null 2>&1 && break
  sleep 2
done
if ! curl -sf -m 5 --resolve "${RESOLVE}" "${PING}" >/dev/null 2>&1; then
  echo "gunicorn did not come up at ${PING}. Last log lines:" >&2
  tail -20 /tmp/ags-gunicorn.log >&2
  echo "--- direct response ---" >&2
  curl -s -m 5 --resolve "${RESOLVE}" "${PING}" 2>&1 | head -5 >&2
  exit 1
fi
echo "   up. resident set:"
ps -o rss=,comm= -p "${GUNICORN_PID}" $(pgrep -P "${GUNICORN_PID}" 2>/dev/null) 2>/dev/null \
  | awk '{ total += $1; print "     " $2 " " int($1/1024) " MB" } END { print "     total " int(total/1024) " MB" }'

cd "${REPO_ROOT}/load-tests/k6" || exit 1

if [ "${MODE}" = "calibrate" ] || [ "${MODE}" = "both" ]; then
  say "Calibration — finding the knee on one node"
  k6 run \
    -e "BASE_URL=http://${SITE}:${PORT}" \
    -e "SITE_HOST=${SITE}" \
    -e "WORKERS=${WORKERS}" \
    -e "PEAK_RPS=${PEAK_RPS}" \
    -e "USER=Administrator" \
    -e "PASSWORD=${ADMIN_PASSWORD}" \
    --no-usage-report \
    calibrate.js
fi

if [ "${MODE}" = "school-day" ] || [ "${MODE}" = "both" ]; then
  # The profile is written for the deployed topology: 6 nodes x 17 workers =
  # 102. Run unscaled against ${WORKERS} workers it breaches every threshold no
  # matter how healthy the build is, and a test that can only fail proves
  # nothing. Scaling every cohort by the worker ratio keeps the shape of the day
  # and makes the pass/fail meaningful for this box.
  MODEL_WORKERS=${MODEL_WORKERS:-102}
  SCALE=${SCALE:-$(( (MODEL_WORKERS + WORKERS - 1) / WORKERS ))}

  say "School-day profile (scaled 1/${SCALE})"
  echo "   ${WORKERS} workers here vs ${MODEL_WORKERS} in docs/capacity-model.md, so every"
  echo "   cohort is divided by ${SCALE}. A pass means this build sustains its"
  echo "   proportional share of the design load. It is NOT a 2,500-user result;"
  echo "   only an unscaled run against the full topology is that."
  k6 run \
    -e "BASE_URL=http://${SITE}:${PORT}" \
    -e "SITE_HOST=${SITE}" \
    -e "SCALE=${SCALE}" \
    -e "PARENT_USER=Administrator" -e "PARENT_PASSWORD=${ADMIN_PASSWORD}" \
    -e "TEACHER_USER=Administrator" -e "TEACHER_PASSWORD=${ADMIN_PASSWORD}" \
    -e "STAFF_USER=Administrator" -e "STAFF_PASSWORD=${ADMIN_PASSWORD}" \
    --no-usage-report \
    school-day.js
fi
