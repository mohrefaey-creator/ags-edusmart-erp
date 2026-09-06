#!/usr/bin/env bash
# Seed synthetic volume so the load test measures something real.
#
#   sudo bash scripts/seed-loadtest.sh [students]
#
# Kept as a script rather than an inline bench command because the --kwargs
# payload is a JSON literal inside a shell string inside `su -c` inside the WSL
# invocation, and every layer of that has its own opinion about braces and
# quotes. A file has no layers.
set -uo pipefail

BENCH_DIR=${BENCH_DIR:-/home/frappe/frappe-bench}
BENCH_USER=${BENCH_USER:-frappe}
SITE=${SITE:-ags.localhost}
STUDENTS=${1:-200}

# Frappe refuses to run as root, and a root-run bench also leaves root-owned
# files in the bench directory that later break the frappe user.
if [ "$(id -u)" -eq 0 ] && id -u "${BENCH_USER}" >/dev/null 2>&1; then
  exec su - "${BENCH_USER}" -c \
    "BENCH_DIR='${BENCH_DIR}' SITE='${SITE}' bash '${BASH_SOURCE[0]}' '${STUDENTS}'"
fi

cd "${BENCH_DIR}" || { echo "no bench at ${BENCH_DIR}" >&2; exit 1; }
export PATH="${HOME}/.local/bin:${PATH}"

echo "seeding ${STUDENTS} synthetic students into ${SITE}"
echo "(idempotent — tops up to the target rather than duplicating)"

bench --site "${SITE}" execute ags_edusmart.setup.loadtest_data.seed \
  --kwargs "{'students': ${STUDENTS}}"
status=$?

echo
echo "row counts:"
bench --site "${SITE}" execute ags_edusmart.setup.loadtest_data.stats

# KPI dashboard reads are ~15% of the calibration mix. With no snapshots they
# return an empty list in microseconds, which would flatter the measurement.
echo
echo "refreshing KPI snapshots so dashboard reads hit real rows:"
bench --site "${SITE}" execute ags_edusmart.ags_dashboards.kpi_engine.refresh_due_kpis

exit "${status}"
