#!/usr/bin/env bash
# Why did this pod's container last die?
#
#   sudo bash scripts/k8s-why-restarting.sh [pod]
#
# lastState.terminated carries the reason and exit code, which distinguishes the
# two cases that look identical in `get pods`: the kubelet killed it (a failing
# probe) versus the kernel killed it (OOMKilled). They need opposite fixes.
set -uo pipefail
NS=${NS:-ags-erp}

pod=${1:-}
if [ -z "${pod}" ]; then
  pod=$(kubectl -n "${NS}" get pods --no-headers 2>/dev/null \
        | grep '^ags-web' | grep Running | tail -1 | tr -s ' ' | cut -d' ' -f1)
fi
[ -n "${pod}" ] || { echo "no pod" >&2; exit 1; }
echo "pod: ${pod}"

echo
echo "=== last termination ==="
kubectl -n "${NS}" get pod "${pod}" -o jsonpath='{range .status.containerStatuses[*]}{.name}{"  restarts="}{.restartCount}{"  reason="}{.lastState.terminated.reason}{"  exit="}{.lastState.terminated.exitCode}{"\n"}{end}'

echo
echo "=== resource limits vs node ==="
kubectl -n "${NS}" get pod "${pod}" -o jsonpath='{range .spec.containers[*]}{.name}{"  requests="}{.resources.requests}{"  limits="}{.resources.limits}{"\n"}{end}'

echo
echo "=== recent events ==="
kubectl -n "${NS}" describe pod "${pod}" 2>/dev/null | sed -n '/Events:/,$p' | tail -8

echo
echo "=== last 6 log lines before the restart ==="
kubectl -n "${NS}" logs "${pod}" -c frappe --previous --tail=6 2>&1 | tail -8
