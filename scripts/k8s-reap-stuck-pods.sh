#!/usr/bin/env bash
# Force-remove pods stuck in Terminating.
#
#   sudo bash scripts/k8s-reap-stuck-pods.sh
#
# A pod that is Terminating still holds its memory *request* against the node,
# so on a single small node a handful of stuck pods take the scheduler below the
# threshold for anything new and every subsequent pod sits in Pending with
# "Insufficient memory" — which reads as the manifests asking for too much,
# rather than as dead pods refusing to leave.
#
# They get stuck here because the WSL VM is killed mid-termination often enough
# that the kubelet never finishes the shutdown. On a real cluster this is a
# symptom worth investigating, not a routine cleanup; here it is routine.
set -uo pipefail

NS=${NS:-ags-erp}

stuck=$(kubectl -n "${NS}" get pods --no-headers 2>/dev/null \
        | grep Terminating | cut -d' ' -f1)

if [ -z "${stuck}" ]; then
  echo "no pods stuck in Terminating"
  exit 0
fi

for pod in ${stuck}; do
  echo "   force-deleting ${pod}"
  kubectl -n "${NS}" delete pod "${pod}" --force --grace-period=0 >/dev/null 2>&1
done

echo
kubectl -n "${NS}" get pods 2>&1 | head -15
