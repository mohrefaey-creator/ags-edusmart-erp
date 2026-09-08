#!/usr/bin/env bash
set -uo pipefail
cd /home/frappe/frappe-bench
echo "=== install_fixtures module ==="
ls apps/erpnext/erpnext/setup/setup_wizard/operations/ 2>/dev/null
echo
echo "=== public functions in install_fixtures ==="
grep -nE "^def " apps/erpnext/erpnext/setup/setup_wizard/operations/install_fixtures.py | head -20
echo
echo "=== does it create UOM / Warehouse Type / Item Group? ==="
grep -nE "\"(UOM|Warehouse Type|Item Group)\"" apps/erpnext/erpnext/setup/setup_wizard/operations/install_fixtures.py | head -10
