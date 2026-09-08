#!/usr/bin/env bash
# Run the ags_edusmart test suite against the deployed site.
#
#   sudo bash scripts/run-app-tests.sh [--full]
#
# This is the first thing that says anything about whether the application is
# CORRECT. Everything else in scripts/ checks that it starts.
#
# It scales the tiers it does not need to zero first. Tests need MariaDB, Redis
# and one pod to run in — not the web tier, not socketio, not three worker
# queues — and on a node this small the difference is whether the run finishes
# or gets OOM-killed halfway through.
set -uo pipefail

NS=${NS:-ags-erp}
SITE=${SITE:-ags.localhost}
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bash "${REPO_ROOT}/scripts/k8s-ensure-node.sh" 2>&1 | tail -1
bash "${REPO_ROOT}/scripts/k8s-reap-stuck-pods.sh" >/dev/null 2>&1

echo "freeing the node: scaling web, socketio and two worker queues to zero"
kubectl -n "${NS}" scale deployment/ags-web deployment/ags-socketio \
  deployment/ags-worker-short deployment/ags-worker-long --replicas=0 >/dev/null 2>&1
kubectl -n "${NS}" scale statefulset/ags-scheduler --replicas=0 >/dev/null 2>&1
kubectl -n "${NS}" scale deployment/ags-worker-default --replicas=1 >/dev/null 2>&1

for d in mariadb redis-cache redis-queue ags-worker-default; do
  kubectl -n "${NS}" rollout status "deployment/${d}" --timeout=600s 2>&1 | tail -1
done

pod=$(kubectl -n "${NS}" get pods --no-headers 2>/dev/null \
      | grep '^ags-worker-default' | grep Running | tail -1 | tr -s ' ' | cut -d' ' -f1)
[ -n "${pod}" ] || { echo "no worker pod to run tests in" >&2; exit 1; }
echo "running tests in ${pod}"
echo

# --site, not a throwaway test site: creating a second site means a second
# `bench new-site` on a node that can barely hold one.
kubectl -n "${NS}" exec "${pod}" -c worker -- \
  bench --site "${SITE}" run-tests --app ags_edusmart 2>&1 | tail -60
