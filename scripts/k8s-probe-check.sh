#!/usr/bin/env bash
# Ask the web pod the exact question its health probes ask, and a few variants.
#
#   sudo bash scripts/k8s-probe-check.sh
#
# A failing HTTP probe reports a status code and nothing else, and a 404 from a
# Frappe pod has two very different causes that look identical from outside:
#
#   the route does not exist        -> Werkzeug's own 404 page
#   the site cannot be resolved     -> Frappe's 404, because the probe connects
#                                     to the pod IP and sends that as Host
#
# So every path is asked twice, once as the kubelet asks it and once naming the
# site. Same code both times means the path is wrong; different codes mean the
# app is healthy and the probe simply cannot name the site.
set -uo pipefail

NS=${NS:-ags-erp}
SITE=${SITE:-ags.localhost}
PATHS=${PATHS:-"/api/method/ping /api/method/frappe.ping /api/method/frappe.auth.get_logged_user /"}

pod=$(kubectl -n "${NS}" get pods --no-headers 2>/dev/null \
      | grep '^ags-web' | grep Running | head -1 | tr -s ' ' | cut -d' ' -f1)
if [ -z "${pod}" ]; then
  echo "no running ags-web pod" >&2
  exit 1
fi
con=$(kubectl -n "${NS}" get pod "${pod}" -o jsonpath='{.spec.containers[0].name}')
echo "pod: ${pod} (container ${con})"
echo

for path in ${PATHS}; do
  bare=$(kubectl -n "${NS}" exec "${pod}" -c "${con}" -- \
         curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
         "http://127.0.0.1:8000${path}" 2>/dev/null)
  withhost=$(kubectl -n "${NS}" exec "${pod}" -c "${con}" -- \
             curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
             --header "Host: ${SITE}" "http://127.0.0.1:8000${path}" 2>/dev/null)
  printf '  %-48s no-Host=%s  Host=%s\n' "${path}" "${bare:-ERR}" "${withhost:-ERR}"
done

echo
echo "body of /api/method/frappe.ping:"
kubectl -n "${NS}" exec "${pod}" -c "${con}" -- \
  curl -s --max-time 10 http://127.0.0.1:8000/api/method/frappe.ping 2>/dev/null | head -3
