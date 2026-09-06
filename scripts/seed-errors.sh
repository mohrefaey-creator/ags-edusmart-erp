#!/usr/bin/env bash
# Show why loadtest_data.seed skipped families.
#
# seed() logs each failure to the Error Log and continues, so a run can report
# progress and still have created very little. This prints the distinct causes.
set -uo pipefail

BENCH_DIR=${BENCH_DIR:-/home/frappe/frappe-bench}
SITE=${SITE:-ags.localhost}
config="${BENCH_DIR}/sites/${SITE}/site_config.json"

db=$(grep -o '"db_name"[^,]*' "${config}" | cut -d'"' -f4)
MYSQL_PWD=$(grep -o '"db_password"[^,}]*' "${config}" | cut -d'"' -f4)
export MYSQL_PWD

echo "== failure count"
mysql -N -B -u "${db}" "${db}" -e \
  "select count(*) from \`tabError Log\` where method = 'AGS load-test seed failed';"

echo
echo "== distinct causes (last line of each traceback)"
mysql -N -B -u "${db}" "${db}" -e \
  "select substring_index(trim(trailing '\n' from error), '\n', -1) as cause, count(*)
     from \`tabError Log\`
    where method = 'AGS load-test seed failed'
    group by cause
    order by count(*) desc
    limit 10;"

echo
echo "== one full traceback"
mysql -N -B -u "${db}" "${db}" -e \
  "select error from \`tabError Log\`
    where method = 'AGS load-test seed failed'
    order by creation desc limit 1;" | tail -25
