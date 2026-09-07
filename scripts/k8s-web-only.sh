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
# It also deletes superseded ReplicaSets rather than their pods. A rollout that
# never finishes leaves the old ReplicaSet with a non-zero desired count, so
# deleting its pod just makes it create another one running the old image —
# which then gets tested by mistake.
set -uo pipefail

NS=${NS:-ags-erp}
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bash "${REPO_ROOT}/scripts/k8s-ensure-node.sh" 2>&1 | tail -1
bash "${REPO_ROOT}/scripts/k8s-reap-stuck-pods.sh" >/dev/null 2>&1

echo "scaling the other app tiers to zero"
kubectl -n "${NS}" scale deployment/ags-socketio deployment/ags-worker-short \
  deployment/ags-worker-default deployment/ags-worker-long --replicas=0 >/dev/null 2>&1
kubectl -n "${NS}" scale statefulset/ags-scheduler --replicas=0 >/dev/null 2>&1

current=$(kubectl -n "${NS}" describe deployment ags-web 2>/dev/null \
          | grep 'NewReplicaSet' | tr -s ' ' | cut -d' ' -f2)
echo "current web ReplicaSet: ${current:-unknown}"
for rs in $(kubectl -n "${NS}" get rs --no-headers 2>/dev/null \
            | grep '^ags-web' | tr -s ' ' | cut -d' ' -f1); do
  if [ "${rs}" != "${current}" ]; then
    echo "   deleting superseded ReplicaSet ${rs}"
    kubectl -n "${NS}" delete rs "${rs}" --cascade=foreground >/dev/null 2>&1
  fi
done

echo "waiting for the datastores"
for d in mariadb redis-cache redis-queue; do
  kubectl -n "${NS}" rollout status "deployment/${d}" --timeout=600s 2>&1 | tail -1
done

echo "waiting for web"
kubectl -n "${NS}" rollout status deployment/ags-web --timeout=900s 2>&1 | tail -2
echo
kubectl -n "${NS}" get pods 2>&1 | head -8
