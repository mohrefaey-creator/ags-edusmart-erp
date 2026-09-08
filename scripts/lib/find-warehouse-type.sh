#!/usr/bin/env bash
# Runs INSIDE the container. Where is erpnext supposed to create Warehouse Type
# records, and did it?
set -uo pipefail
cd /home/frappe/frappe-bench
echo "=== erpnext source: who creates Warehouse Type records ==="
grep -rn "Warehouse Type" apps/erpnext --include=*.py \
  | grep -iE "insert|new_doc|get_doc|create" | head -10
echo
echo "=== is it a fixture / setup-wizard record? ==="
grep -rln "warehouse_type" apps/erpnext/erpnext/setup 2>/dev/null | head -10
