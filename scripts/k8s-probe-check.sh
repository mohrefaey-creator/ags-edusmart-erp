#!/usr/bin/env bash
# Ask the web pod the exact question its health probes ask, and a few variants.
#
#   sudo bash scripts/k8s-probe-check.sh [pod]
#
# A failing HTTP probe reports a status code and nothing else, and a 404 from a
# Frappe pod has two very different causes that look identical from outside:
#
#   the route is not registered   -> Werkzeug's own 404 page. Frappe was started
#                                    from the wrong directory, found no sites,
#                                    and built an empty URL map.
#   the site cannot be resolved   -> Frappe's 404, because a kubelet probe
#                                    connects to the pod IP and sends that as
#                                    the Host header.
#
# So every path is asked twice, once as the kubelet asks it and once naming the
# site. Same code both times points at the app or the path; different codes mean
# the app is healthy and the probe simply cannot name the site.
set -uo pipefail

NS=${NS:-ags-erp}
SITE=${SITE:-ags.localhost}
PATHS=${PATHS:-"/api/method/ping /api/method/frappe.ping /api/method/frappe.auth.get_logged_user /"}

# Newest pod by default: for a while after a rollout the old one is also
# Running, and checking that tells you about the image you just replaced.
pod=${1:-}
if [ -z "${pod}" ]; then
  pod=$(kubectl -n "${NS}" get pods --no-headers 2>/dev/null \
        | grep '^ags-web' | grep Running | tail -1 | tr -s ' ' | cut -d' ' -f1)
fi
[ -n "${pod}" ] || { echo "no running ags-web pod" >&2; exit 1; }
echo "pod: ${pod}"
echo

for path in ${PATHS}; do
  bare=$(kubectl -n "${NS}" exec "${pod}" -c frappe -- \
         curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
         "http://127.0.0.1:8000${path}" 2>/dev/null)
  withhost=$(kubectl -n "${NS}" exec "${pod}" -c frappe -- \
             curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
             --header "Host: ${SITE}" "http://127.0.0.1:8000${path}" 2>/dev/null)
  printf '  %-48s no-Host=%s  Host=%s\n' "${path}" "${bare:-ERR}" "${withhost:-ERR}"
done
