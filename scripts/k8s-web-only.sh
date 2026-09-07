#!/usr/bin/env bash
# Bring up the web tier alone, to test it on a node that cannot hold everything.
#
#   sudo bash scripts/k8s-web-only.sh
#
# The workers, the scheduler and socketio together request more memory than is
# left after MariaDB and Redis, and a web pod that cannot be scheduled — or that
# is evicted seconds after starting — cannot be tested. This scales them to zero
# so there is room, and leaves the datastores alone because web needs them.
#
# socketio stays at zero afterwards regardless: its node_modules fix needs a
# full image rebuild, so it crash-loops on any image patch-runtime-image.sh
# produces, and a crash-looping pod is not free.
set -uo pipefail

NS=${NS:-ags-erp}
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bash "${REPO_ROOT}/scripts/k8s-ensure-node.sh" 2>&1 | tail -1
bash "${REPO_ROOT}/scripts/k8s-reap-stuck-pods.sh" >/dev/null 2>&1

echo "scaling the other app tiers to zero"
kubectl -n "${NS}" scale deployment/ags-socketio deployment/ags-worker-short \
  deployment/ags-worker-default deployment/ags-worker-long --replicas=0 >/dev/null 2>&1
kubectl -n "${NS}" scale statefulset/ags-scheduler --replicas=0 >/dev/null 2>&1

echo "removing web pods from superseded ReplicaSets"
current=$(kubectl -n "${NS}" describe deployment ags-web 2>/dev/null \
          | grep 'NewReplicaSet' | tr -s ' ' | cut -d' ' -f2)
for p in $(kubectl -n "${NS}" get pods --no-headers 2>/dev/null \
           | grep '^ags-web' | tr -s ' ' | cut -d' ' -f1); do
  case "${p}" in
    ${current}-*) : ;;
    *) echo "   deleting stale ${p}"
       kubectl -n "${NS}" delete pod "${p}" --force --grace-period=0 >/dev/null 2>&1 ;;
  esac
done

echo "waiting for web"
kubectl -n "${NS}" rollout status deployment/ags-web --timeout=900s 2>&1 | tail -2
kubectl -n "${NS}" get pods 2>&1 | head -8
