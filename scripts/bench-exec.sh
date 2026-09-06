#!/usr/bin/env bash
# Run one dotted bench method as the frappe user.
#
#   sudo bash scripts/bench-exec.sh ags_edusmart.setup.permissions.apply_permissions
#   sudo bash scripts/bench-exec.sh some.method "{'key': 'value'}"
#
# Exists because the equivalent one-liner has to survive PowerShell, then wsl,
# then `bash -lc`, then `su -c`, and each of those has its own opinion about
# quotes, $VAR and parentheses. The last attempt died on the parentheses inside
# an expanded $PATH. A file has none of those layers.
set -uo pipefail

BENCH_DIR=${BENCH_DIR:-/home/frappe/frappe-bench}
BENCH_USER=${BENCH_USER:-frappe}
SITE=${SITE:-ags.localhost}
METHOD=${1:?usage: bench-exec.sh <dotted.method> [kwargs-json]}
KWARGS=${2:-}

if [ "$(id -u)" -eq 0 ] && id -u "${BENCH_USER}" >/dev/null 2>&1; then
  exec su - "${BENCH_USER}" -c \
    "BENCH_DIR='${BENCH_DIR}' SITE='${SITE}' bash '${BASH_SOURCE[0]}' '${METHOD}' '${KWARGS}'"
fi

cd "${BENCH_DIR}" || { echo "no bench at ${BENCH_DIR}" >&2; exit 1; }
export PATH="${HOME}/.local/bin:${PATH}"

if [ -n "${KWARGS}" ]; then
  exec bench --site "${SITE}" execute "${METHOD}" --kwargs "${KWARGS}"
fi
exec bench --site "${SITE}" execute "${METHOD}"
