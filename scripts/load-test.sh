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
# Password for the three role-scoped load-test users. Local, disposable, and
# only ever valid on a site that already allows seeding (developer/allow_tests).
LOADTEST_PASSWORD=${LOADTEST_PASSWORD:-loadtest-not-real}
MODEL_WORKERS=${MODEL_WORKERS:-102}
# Empty means "derive from the worker ratio below"; SCALE=1 means unscaled.
SCALE=${SCALE:-}
# Simulated minutes per real second. 60 runs a full day in ~8 minutes; raise it
# for a quick diagnostic run that keeps the shape but not the duration.
COMPRESSION=${COMPRESSION:-60}
# Distinct accounts per cohort. See the note by the ensure_users call below.
USER_POOL=${USER_POOL:-30}
MODE=${1:-both}

if [ "$(id -u)" -eq 0 ] && id -u "${BENCH_USER}" >/dev/null 2>&1; then
  # Every tuneable has to cross this boundary explicitly.
  #
  # `su -` starts a login shell with a clean environment, so anything not named
  # here is silently replaced by its default on the other side. That has now
  # cost two runs: ADMIN_PASSWORD went missing and every login failed, then
  # SCALE went missing and a run invoked as SCALE=1 quietly executed at 1/26 —
  # producing a real-looking result for a test nobody asked for.
  exec su - "${BENCH_USER}" -c \
    "BENCH_DIR='${BENCH_DIR}' SITE='${SITE}' PORT='${PORT}' WORKERS='${WORKERS}' \
     PEAK_RPS='${PEAK_RPS}' ADMIN_PASSWORD='${ADMIN_PASSWORD}' \
     LOADTEST_PASSWORD='${LOADTEST_PASSWORD}' MODEL_WORKERS='${MODEL_WORKERS}' \
     SCALE='${SCALE}' COMPRESSION='${COMPRESSION}' USER_POOL='${USER_POOL}' \
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

say "Ensuring pooled, role-scoped load-test users (${USER_POOL} per cohort)"
# A pool, not Administrator and not one account per cohort.
#
# Administrator bypasses permission checks, so it would skip the row-scoping
# subqueries the capacity model's design rests on. And concurrent logins for one
# account collide inside Frappe's own session bookkeeping and return 500 — about
# half of 30 simultaneous logins did, which turned a healthy run into a 94%
# failure rate that read as an application fault. Production has one login per
# person; a pool reproduces that rather than papering over it.
(
  cd "${BENCH_DIR}" || exit 1
  export PATH="${HOME}/.local/bin:${PATH}"
  bench --site "${SITE}" execute ags_edusmart.setup.loadtest_data.ensure_users \
    --kwargs "{'password': '${LOADTEST_PASSWORD}', 'per_cohort': ${USER_POOL}}"
) || { echo "could not create load-test users" >&2; exit 1; }

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
  # Empty (not unset) means the caller did not choose, so derive it.
  [ -n "${SCALE}" ] || SCALE=$(( (MODEL_WORKERS + WORKERS - 1) / WORKERS ))

  if [ "${SCALE}" -eq 1 ]; then
    say "School-day profile (UNSCALED — full 2,500-user shape)"
    echo "   Every cohort at full size against ${WORKERS} workers. This is the"
    echo "   real shape of the day; whether it passes here is a statement about"
    echo "   this box, not about the ${MODEL_WORKERS}-worker topology."
  else
    say "School-day profile (scaled 1/${SCALE})"
    echo "   ${WORKERS} workers here vs ${MODEL_WORKERS} in docs/capacity-model.md, so every"
    echo "   cohort is divided by ${SCALE}. A pass means this build sustains its"
    echo "   proportional share of the design load. It is NOT a 2,500-user result;"
    echo "   only an unscaled run against the full topology is that."
  fi
  k6 run \
    -e "BASE_URL=http://${SITE}:${PORT}" \
    -e "SITE_HOST=${SITE}" \
    -e "SCALE=${SCALE}" \
    -e "COMPRESSION=${COMPRESSION}" \
    -e "USER_POOL=${USER_POOL}" \
    -e "PARENT_PASSWORD=${LOADTEST_PASSWORD}" \
    -e "TEACHER_PASSWORD=${LOADTEST_PASSWORD}" \
    -e "STAFF_PASSWORD=${LOADTEST_PASSWORD}" \
    --no-usage-report \
    school-day.js
fi
