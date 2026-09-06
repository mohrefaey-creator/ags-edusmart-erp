#!/usr/bin/env bash
# Run bench migrate on the dev site, as the frappe user.
#
#   sudo bash scripts/migrate.sh
#
# The deployment repo runs migrate as its own Kubernetes Job before every
# rollout (infra/k8s/40-migrate-job-netpol.yaml), so being able to run exactly
# that step locally is how a DocType or permission change gets proven before it
# reaches a cluster.
set -uo pipefail

BENCH_DIR=${BENCH_DIR:-/home/frappe/frappe-bench}
BENCH_USER=${BENCH_USER:-frappe}
SITE=${SITE:-ags.localhost}

if [ "$(id -u)" -eq 0 ] && id -u "${BENCH_USER}" >/dev/null 2>&1; then
  exec su - "${BENCH_USER}" -c \
    "BENCH_DIR='${BENCH_DIR}' SITE='${SITE}' bash '${BASH_SOURCE[0]}'"
fi

cd "${BENCH_DIR}" || { echo "no bench at ${BENCH_DIR}" >&2; exit 1; }
export PATH="${HOME}/.local/bin:${PATH}"

exec bench --site "${SITE}" migrate
