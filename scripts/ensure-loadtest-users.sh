#!/usr/bin/env bash
# Create the pooled, role-scoped users the school-day profile signs in as.
#
#   sudo bash scripts/ensure-loadtest-users.sh [per_cohort]
#
# load-test.sh calls this itself; it is separate so the pool can be built (and
# checked) without paying for a full load run. Idempotent.
set -uo pipefail

BENCH_DIR=${BENCH_DIR:-/home/frappe/frappe-bench}
BENCH_USER=${BENCH_USER:-frappe}
SITE=${SITE:-ags.localhost}
LOADTEST_PASSWORD=${LOADTEST_PASSWORD:-loadtest-not-real}
PER_COHORT=${1:-30}

if [ "$(id -u)" -eq 0 ] && id -u "${BENCH_USER}" >/dev/null 2>&1; then
  exec su - "${BENCH_USER}" -c \
    "BENCH_DIR='${BENCH_DIR}' SITE='${SITE}' LOADTEST_PASSWORD='${LOADTEST_PASSWORD}' \
     bash '${BASH_SOURCE[0]}' '${PER_COHORT}'"
fi

cd "${BENCH_DIR}" || { echo "no bench at ${BENCH_DIR}" >&2; exit 1; }
export PATH="${HOME}/.local/bin:${PATH}"

exec bench --site "${SITE}" execute \
  ags_edusmart.setup.loadtest_data.ensure_users \
  --kwargs "{'password': '${LOADTEST_PASSWORD}', 'per_cohort': ${PER_COHORT}}"
