#!/usr/bin/env bash
# Runs INSIDE the container. Installs apps one at a time and reports, at each
# step, whether the Warehouse Type records erpnext's company setup depends on
# actually exist — and which app creates a Company.
# Expects: SITE, DB_HOST, REDIS_HOST, DB_ROOT_PASSWORD, ADMIN_PASSWORD
set -uo pipefail
cd /home/frappe/frappe-bench

bench set-config -g db_host "${DB_HOST}"
bench set-config -g db_port 3306
bench set-config -g redis_cache "redis://${REDIS_HOST}:6379"
bench set-config -g redis_queue "redis://${REDIS_HOST}:6379"
bench set-config -g redis_socketio "redis://${REDIS_HOST}:6379"

bench new-site "${SITE}"   --db-root-password "${DB_ROOT_PASSWORD}"   --admin-password "${ADMIN_PASSWORD}"   --mariadb-user-host-login-scope='%' >/dev/null 2>&1

probe() {
  bench --site "${SITE}" console <<'PY' 2>/dev/null | grep -E '^PROBE'
import frappe
wt = frappe.get_all("Warehouse Type", pluck="name") if frappe.db.table_exists("tabWarehouse Type") else "no table"
co = frappe.get_all("Company", pluck="name") if frappe.db.table_exists("tabCompany") else "no table"
wh = frappe.get_all("Warehouse", pluck="name") if frappe.db.table_exists("tabWarehouse") else "no table"
print("PROBE warehouse_types:", wt)
print("PROBE companies:", co)
print("PROBE warehouses:", wh)
PY
}

echo "### after frappe only"
probe

for app in erpnext payments hrms education ags_edusmart; do
  echo
  echo "### installing ${app}"
  if bench --site "${SITE}" install-app "${app}" >/tmp/${app}.log 2>&1; then
    echo "### ${app} OK"
  else
    echo "### ${app} FAILED — last lines:"
    grep -E 'Error|error|Exception|Could not find' /tmp/${app}.log | tail -5
  fi
  probe
done
