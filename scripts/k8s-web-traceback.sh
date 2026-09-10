#!/usr/bin/env bash
# Show the traceback behind a 500 from the web tier's startup probe.
#
#   sudo bash scripts/k8s-web-traceback.sh
#
# A probe reports "HTTP probe failed with statuscode: 500" and nothing else. The
# traceback is in the pod's log, but the pod restarts every couple of minutes,
# so this looks at both the current container and the one before it.
set -uo pipefail
NS=${NS:-ags-erp}

pod=${1:-}
if [ -z "${pod}" ]; then
  pod=$(kubectl -n "${NS}" get pods --no-headers 2>/dev/null \
        | grep '^ags-web' | tail -1 | tr -s ' ' | cut -d' ' -f1)
fi
[ -n "${pod}" ] || { echo "no ags-web pod" >&2; exit 1; }
echo "pod: ${pod}"

for which in "" "--previous"; do
  echo
  echo "=== logs ${which:-(current)} ==="
  # shellcheck disable=SC2086
  kubectl -n "${NS}" logs "${pod}" -c frappe ${which} --tail=200 2>/dev/null \
    | grep -A30 'Traceback' | head -45
done
