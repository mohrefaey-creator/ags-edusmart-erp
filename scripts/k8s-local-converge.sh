#!/usr/bin/env bash
# Drive an existing local cluster to a healthy state, and be safe to re-run.
#
#   sudo bash scripts/k8s-local-converge.sh
#
# k8s-local-up.sh is the deploy. This is the thing you run after the WSL VM has
# been killed underneath it — which on a 4 GB VM whose host runs out of memory
# is often. It assumes the image and the cluster already exist and only fixes
# up what a hard stop leaves behind:
#
#   * the node container stopped, so kubectl talks to nothing
#   * pods stuck Terminating, still holding their memory requests against the
#     node, so everything else sits in Pending on "Insufficient memory"
#   * containerd holding a sandbox name reservation from a pod that never
#     finished starting, so the replacement pod cannot start either
#   * the Jobs needing to run in order, site-init before migrate
#
# Every step is idempotent, so the answer to a crash halfway through is to run
# it again.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NS=${NS:-ags-erp}
OVERLAY="${REPO_ROOT}/infra/k8s-local"

say()  { printf '\n\033[1m== %s\033[0m\n' "$1"; }
note() { printf '   %s\n' "$1"; }

say "Node"
bash "${REPO_ROOT}/scripts/start-docker.sh" >/dev/null 2>&1
bash "${REPO_ROOT}/scripts/k8s-ensure-node.sh" 2>&1 | tail -1

say "Clearing what the last hard stop left behind"
bash "${REPO_ROOT}/scripts/k8s-reap-stuck-pods.sh" >/dev/null 2>&1
note "stuck pods reaped"

# A pod that never got a sandbox leaves containerd holding its name, and the
# kubelet then refuses to start any replacement with the same name. Deleting
# the pod is not enough — the Job must mint a new pod name.
sandbox_stuck=$(kubectl -n "${NS}" get events 2>/dev/null \
                | grep -c "is reserved for" || true)
if [ "${sandbox_stuck:-0}" -gt 0 ]; then
  note "containerd is holding stale sandbox names — restarting the node"
  docker restart ags-erp-control-plane >/dev/null 2>&1
  bash "${REPO_ROOT}/scripts/k8s-ensure-node.sh" >/dev/null 2>&1
  bash "${REPO_ROOT}/scripts/k8s-reap-stuck-pods.sh" >/dev/null 2>&1
fi

say "Datastores"
kubectl apply -k "${OVERLAY}" >/dev/null 2>&1
for d in mariadb redis-cache redis-queue; do
  kubectl -n "${NS}" rollout status "deployment/${d}" --timeout=600s 2>&1 | tail -1
done

# site-init before migrate. Applying both together makes migrate race the site
# it is supposed to migrate, and it loses with `404 ... does not exist`.
say "Site init"
kubectl -n "${NS}" delete job ags-site-init --ignore-not-found --wait=true >/dev/null 2>&1
kubectl apply -k "${OVERLAY}" >/dev/null 2>&1
if kubectl -n "${NS}" wait --for=condition=complete job/ags-site-init --timeout=1800s >/dev/null 2>&1; then
  note "site-init complete"
else
  note "site-init did NOT complete — last lines:"
  kubectl -n "${NS}" logs job/ags-site-init -c site-init --tail=15 2>&1 | sed 's/^/     /'
  exit 1
fi

say "Migrate"
kubectl -n "${NS}" delete job ags-migrate --ignore-not-found --wait=true >/dev/null 2>&1
kubectl apply -k "${OVERLAY}" >/dev/null 2>&1
if kubectl -n "${NS}" wait --for=condition=complete job/ags-migrate --timeout=1800s >/dev/null 2>&1; then
  note "migrate complete"
else
  note "migrate did NOT complete — last lines:"
  kubectl -n "${NS}" logs job/ags-migrate -c migrate --tail=15 2>&1 | sed 's/^/     /'
  exit 1
fi

say "App tiers"
# Restarted rather than just applied: the pods that are already running predate
# the site_config the Jobs just wrote, and Frappe reads it at startup.
kubectl -n "${NS}" rollout restart deployment/ags-web deployment/ags-socketio \
    deployment/ags-worker-short deployment/ags-worker-default \
    deployment/ags-worker-long statefulset/ags-scheduler >/dev/null 2>&1
for w in deployment/ags-web deployment/ags-worker-short \
         deployment/ags-worker-default deployment/ags-worker-long \
         statefulset/ags-scheduler; do
  kubectl -n "${NS}" rollout status "${w}" --timeout=900s 2>&1 | tail -1
done
# socketio is deliberately not waited on: its node_modules fix needs a full
# image rebuild, so it crash-loops on any image produced by
# patch-runtime-image.sh.
kubectl -n "${NS}" rollout status deployment/ags-socketio --timeout=120s 2>&1 | tail -1

say "Status"
kubectl -n "${NS}" get pods
