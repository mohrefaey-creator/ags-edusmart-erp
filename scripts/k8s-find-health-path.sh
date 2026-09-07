#!/usr/bin/env bash
# Which URL should the health probes actually use?
#
#   sudo bash scripts/k8s-find-health-path.sh
#
# Asked through the WSGI application directly rather than over HTTP, because a
# pod whose startup probe is failing is being killed every couple of minutes and
# a curl loop against it mostly measures the restarts. This imports the same
# application gunicorn serves, from the same directory, and asks it each
# candidate path with and without a Host header.
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

kubectl -n "${NS}" exec "${pod}" -c frappe -- "${BENCH}/env/bin/python" -W ignore -c "
import os, sys
os.chdir('${BENCH}/sites')
from frappe.app import application
from werkzeug.test import Client

paths = [
    '/',
    '/api/method/ping',
    '/api/method/frappe.ping',
    '/api/method/frappe.handler.ping',
    '/api/method/frappe.utils.change_log.get_versions',
    '/app',
    '/login',
]
print('%-48s %-12s %s' % ('path', 'no-Host', 'Host'))
for p in paths:
    row = []
    for hdrs in ({}, {'Host': '${SITE}'}):
        try:
            row.append(str(Client(application).get(p, headers=hdrs).status_code))
        except Exception as e:
            row.append(type(e).__name__)
    print('%-48s %-12s %s' % (p, row[0], row[1]))
" 2>&1 | grep -v Warning | grep -v '^  ' | tail -12
