#!/usr/bin/env bash
set -uo pipefail
cd /home/frappe/frappe-bench
echo "=== company.py: warehouse creation ==="
grep -n "warehouse_type\|Goods In Transit\|create_default_warehouses" -B2 -A6 \
  apps/erpnext/erpnext/setup/doctype/company/company.py | head -40
echo
echo "=== the v13 patch that creates the record ==="
sed -n '20,40p' apps/erpnext/erpnext/patches/v13_0/stock_entry_enhancements.py
