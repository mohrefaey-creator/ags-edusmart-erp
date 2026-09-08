#!/usr/bin/env bash
# Runs INSIDE the container. Did the Warehouse Type guard actually work?
# Expects: SITE
set -uo pipefail
cd /home/frappe/frappe-bench/sites
python - <<'PY'
import os, frappe, traceback
frappe.init(site=os.environ["SITE"]); frappe.connect()

print("Warehouse Type rows:", frappe.get_all("Warehouse Type", pluck="name"))
print("Company rows       :", frappe.get_all("Company", pluck="name"))

meta = frappe.get_meta("Warehouse Type")
print("autoname           :", meta.autoname)
print("app of ags module  :", frappe.get_module_path("AGS Core") if frappe.db.exists("Module Def","AGS Core") else "n/a")

# Is the working-tree app actually the one loaded?
import ags_edusmart
print("ags_edusmart file  :", ags_edusmart.__file__)
try:
    from ags_edusmart.setup import upstream_fixtures
    print("guard importable   : yes")
    upstream_fixtures.ensure_all()
    frappe.db.commit()
    print("after ensure_all   :", frappe.get_all("Warehouse Type", pluck="name"))
except Exception:
    print("guard FAILED:")
    traceback.print_exc()
PY
