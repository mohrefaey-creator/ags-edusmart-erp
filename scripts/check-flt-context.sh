#!/usr/bin/env bash
# Does frappe's flt() need a site?
#
#   sudo bash scripts/check-flt-context.sh
#
# Written to settle a specific question: three money tests failed with every
# amount collapsing to 0.00 when run without a site, which is either three real
# bugs in the fee and ZATCA code or an artifact of running them with no
# database. flt(x, precision) rounds via frappe's configured rounding method,
# and reading that setting needs a database — so this checks whether flt
# silently returns 0 rather than raising when it cannot.
set -uo pipefail
TAG=${TAG:-ags/edusmart-erp:local}

docker run --rm --entrypoint /bin/bash "${TAG}" -c '
cd /home/frappe/frappe-bench/sites
python - <<PY
import frappe
frappe.init(site="")
from frappe.utils import flt

print("flt(24500)     =", flt(24500))
print("flt(24500, 2)  =", flt(24500, 2))
print("flt(100/3, 2)  =", flt(100/3, 2))

from frappe.utils.data import rounded
try:
    print("rounded(24500, 2) =", rounded(24500, 2))
except Exception as e:
    print("rounded raised:", type(e).__name__, str(e)[:120])
PY
'
