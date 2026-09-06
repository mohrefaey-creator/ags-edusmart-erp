#!/usr/bin/env bash
# Run read-only SQL against a site's database, reading SQL from stdin.
#
#   echo 'select count(*) from tabUser;' | sudo bash scripts/site-sql.sh
#   sudo bash scripts/site-sql.sh < query.sql
#
# Exists so ad-hoc queries stop being written as one-liners nested through
# `wsl -- bash -lc '...'`, where $var and quotes are chewed by three shells
# before mysql sees them. It also keeps the credential out of the command line:
# it is read from site_config.json into MYSQL_PWD, so `ps` never shows it.
set -uo pipefail

BENCH_DIR=${BENCH_DIR:-/home/frappe/frappe-bench}
SITE=${SITE:-ags.localhost}
CONFIG="${BENCH_DIR}/sites/${SITE}/site_config.json"

[ -f "${CONFIG}" ] || { echo "no site_config.json for ${SITE}" >&2; exit 1; }

db=$(grep -o '"db_name"[^,]*' "${CONFIG}" | cut -d'"' -f4)
MYSQL_PWD=$(grep -o '"db_password"[^,}]*' "${CONFIG}" | cut -d'"' -f4)
export MYSQL_PWD

exec mysql --table -u "${db}" "${db}"
