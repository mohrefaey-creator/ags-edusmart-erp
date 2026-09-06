#!/usr/bin/env bash
# What is actually in each bench site, without starting Python.
#
# `bench --site X execute ...` costs ~250 MB of import for a question as small
# as "how many students are there". On a box where memory is the binding
# constraint this asks MariaDB directly instead.
set -uo pipefail

BENCH_DIR=${BENCH_DIR:-/home/frappe/frappe-bench}

for site_dir in "${BENCH_DIR}"/sites/*/; do
  site=$(basename "${site_dir}")
  config="${site_dir}site_config.json"
  [ -f "${config}" ] || continue

  db=$(grep -o '"db_name"[^,]*' "${config}" | cut -d'"' -f4)
  dev=$(grep -o '"developer_mode"[^,}]*' "${config}" | grep -o '[0-9]*$')

  printf '\n== %s\n' "${site}"
  printf '   db              : %s\n' "${db:-<none>}"
  printf '   developer_mode  : %s\n' "${dev:-0}"

  # Read-only counts, using the site's own DB user rather than root — MariaDB
  # root here has a password and does not accept socket auth.
  #
  # The credential is passed through MYSQL_PWD in this process's environment
  # and is never echoed, written to a file, or placed on a command line where
  # `ps` would show it.
  MYSQL_PWD=$(grep -o '"db_password"[^,}]*' "${config}" | cut -d'"' -f4)
  export MYSQL_PWD

  mysql -N -B -u "${db}" "${db}" 2>/dev/null <<'SQL' | while read -r label value; do
select 'apps',       (select group_concat(app_name) from `tabInstalled Application`)
union all select 'students',   (select count(*) from `tabStudent`)
union all select 'synthetic',  (select count(*) from `tabStudent` where last_name = 'LTSynthetic')
union all select 'invoices',   (select count(*) from `tabSales Invoice` where docstatus = 1)
union all select 'fee_plans',  (select count(*) from `tabAGS Fee Plan` where docstatus = 1)
union all select 'gl_entries', (select count(*) from `tabGL Entry` where is_cancelled = 0);
SQL
    printf '   %-15s : %s\n' "${label}" "${value}"
  done || printf '   (tables not present — AGS app may not be installed here)\n'
done
