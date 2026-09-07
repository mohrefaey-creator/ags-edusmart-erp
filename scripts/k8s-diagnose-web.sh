#!/usr/bin/env bash
# Why is the web tier answering 404 to everything?
#
#   sudo bash scripts/k8s-diagnose-web.sh [pod]
#
# Checks, in order, the three things that make Frappe serve Werkzeug's 404 for
# every route while gunicorn itself looks perfectly healthy:
#   1. the working directory gunicorn actually has (not the one the shell gets)
#   2. whether the sites directory is visible from there
#   3. whether frappe can init and connect to the site at all
set -uo pipefail

NS=${NS:-ags-erp}
SITE=${SITE:-ags.localhost}
BENCH=/home/frappe/frappe-bench

pod=${1:-}
if [ -z "${pod}" ]; then
  pod=$(kubectl -n "${NS}" get pods --no-headers 2>/dev/null \
        | grep '^ags-web' | grep Running | tail -1 | tr -s ' ' | cut -d' ' -f1)
fi
[ -n "${pod}" ] || { echo "no running ags-web pod" >&2; exit 1; }
echo "pod: ${pod}"

echo
echo "=== cwd of the gunicorn master (pid 1) ==="
kubectl -n "${NS}" exec "${pod}" -c frappe -- readlink /proc/1/cwd

echo
echo "=== what that cwd contains ==="
kubectl -n "${NS}" exec "${pod}" -c frappe -- ls /proc/1/cwd/

echo
echo "=== can frappe init and connect? ==="
kubectl -n "${NS}" exec "${pod}" -c frappe -- \
  "${BENCH}/env/bin/python" -c "
import os, traceback
os.chdir('${BENCH}/sites')
import frappe
try:
    frappe.init(site='${SITE}')
    frappe.connect()
    print('init + connect OK')
    print('installed apps:', frappe.get_installed_apps())
except Exception:
    traceback.print_exc()
"

echo
echo "=== what the WSGI app returns for / ==="
kubectl -n "${NS}" exec "${pod}" -c frappe -- \
  "${BENCH}/env/bin/python" -c "
import os, traceback
os.chdir('${BENCH}/sites')
try:
    from frappe.app import application
    from werkzeug.test import Client
    r = Client(application).get('/', headers={'Host': '${SITE}'})
    print('status:', r.status)
    print('body head:', r.get_data(as_text=True)[:200].replace(chr(10), ' '))
except Exception:
    traceback.print_exc()
"
