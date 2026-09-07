#!/usr/bin/env bash
# Stand up a throwaway kind cluster and deploy infra/k8s to it.
#
#   sudo bash scripts/k8s-local-up.sh          # full run
#   sudo bash scripts/k8s-local-up.sh --keep   # reuse an existing cluster
#
# This is the cheapest way to find out whether the manifests actually work.
# `kubectl apply --dry-run` proves they parse; it does not prove that the site
# exists, that the volume mount does not hide the app list, that the probes pass
# or that the Job ordering holds. Every one of those was wrong the first time.
#
# What it does NOT prove is in infra/k8s-local/README.md — read that before
# quoting a green run as evidence of anything about production.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLUSTER=${CLUSTER:-ags-erp}
NS=${NS:-ags-erp}
IMAGE=${IMAGE:-ags/edusmart-erp:local}
KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

say() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
die() { printf '\033[31mFATAL: %s\033[0m\n' "$1" >&2; exit 1; }

command -v kind    >/dev/null 2>&1 || die "kind not installed — scripts/install-k8s-tools.sh"
command -v kubectl >/dev/null 2>&1 || die "kubectl not installed — scripts/install-k8s-tools.sh"
docker image inspect "${IMAGE}" >/dev/null 2>&1 || die "${IMAGE} not built — scripts/build-image.sh"

# ---------------------------------------------------------------- cluster
if kind get clusters 2>/dev/null | grep -qx "${CLUSTER}"; then
  if [ "${KEEP}" -eq 1 ]; then
    say "Reusing cluster ${CLUSTER}"
  else
    say "Deleting existing cluster ${CLUSTER}"
    kind delete cluster --name "${CLUSTER}"
  fi
fi

if ! kind get clusters 2>/dev/null | grep -qx "${CLUSTER}"; then
  say "Creating cluster ${CLUSTER}"
  kind create cluster --config "${REPO_ROOT}/infra/k8s-local/kind-cluster.yaml" \
    --wait 180s || die "cluster create failed"
fi

# ------------------------------------------------------------------- node
# On WSL the Docker daemon restarts often enough that this matters: kind's node
# is created with --restart=on-failure:1 and simply stays down afterwards.
say "Checking the node is up"
bash "${REPO_ROOT}/scripts/k8s-ensure-node.sh" || die "node not available"

# ------------------------------------------------------------------ image
# Via a registry, not `kind load`. See scripts/k8s-local-registry.sh: loading
# a 4.35 GB image with `kind load` took the whole WSL VM down, because it
# saves the image to a tar and imports it in one go.
say "Publishing the image to the local registry"
bash "${REPO_ROOT}/scripts/k8s-local-registry.sh" >/dev/null 2>&1 \
  || die "could not publish the image — run scripts/k8s-local-registry.sh to see why"
echo "   localhost:5000/${IMAGE}"

# ---------------------------------------------------------------- secrets
# Generated here, never committed. 00-namespace-config.yaml ships REPLACE_ME
# placeholders precisely so that a real value never lands in git; applying the
# base as-is would give Frappe the literal string REPLACE_ME as a password.
say "Creating namespace and secrets"
kubectl create namespace "${NS}" --dry-run=client -o yaml | kubectl apply -f - >/dev/null

gen() { head -c 24 /dev/urandom | base64 | tr -d '/+=' | head -c 24; }
DB_ROOT_PASSWORD=${DB_ROOT_PASSWORD:-$(gen)}
ADMIN_PASSWORD=${ADMIN_PASSWORD:-$(gen)}
# Frappe encrypts stored credentials with a Fernet key: 32 url-safe base64
# bytes. Anything else fails at first use, not at startup.
ENCRYPTION_KEY=${ENCRYPTION_KEY:-$(head -c 32 /dev/urandom | base64 | tr '+/' '-_')}

kubectl -n "${NS}" create secret generic ags-erp-secrets \
  --from-literal=DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD}" \
  --from-literal=ADMIN_PASSWORD="${ADMIN_PASSWORD}" \
  --from-literal=ENCRYPTION_KEY="${ENCRYPTION_KEY}" \
  --from-literal=ZATCA_CERTIFICATE="local-not-real" \
  --from-literal=ZATCA_SECRET="local-not-real" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
echo "   secrets generated (admin password printed at the end)"

# ----------------------------------------------------------------- apply
# A Job's pod template is immutable, so re-applying a changed Job is rejected
# with `field is immutable` and a full dump of the spec. Both Jobs here are
# idempotent by design and safe to recreate, and this is exactly the sequence
# 40-migrate-job-netpol.yaml documents for a real deploy:
#
#   kubectl -n ags-erp delete job ags-migrate --ignore-not-found
#
# Deleting them before the apply also clears a previous failed run, so `wait
# --for=condition=complete` is not satisfied by a stale Job object.
say "Removing previous Job objects (their pod template is immutable)"
kubectl -n "${NS}" delete job ags-site-init ags-migrate \
  --ignore-not-found --wait=true >/dev/null 2>&1

say "Applying infra/k8s via the local overlay"
# The overlay carries the Secret template too; ours must win, so it is applied
# after and the template's placeholder values are overwritten. Ordering here is
# not cosmetic: applying the base Secret afterwards would set REPLACE_ME.
kubectl apply -k "${REPO_ROOT}/infra/k8s-local" || die "apply failed"

kubectl -n "${NS}" create secret generic ags-erp-secrets \
  --from-literal=DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD}" \
  --from-literal=ADMIN_PASSWORD="${ADMIN_PASSWORD}" \
  --from-literal=ENCRYPTION_KEY="${ENCRYPTION_KEY}" \
  --from-literal=ZATCA_CERTIFICATE="local-not-real" \
  --from-literal=ZATCA_SECRET="local-not-real" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

# ------------------------------------------------------- ordered rollout
# `kubectl apply -k` submits everything at once, so the web tier, the workers
# and the scheduler all start racing the two Jobs they depend on — against a
# site that does not exist yet and a volume that has not been seeded. They do
# eventually converge through CrashLoopBackOff, but on a small node they also
# spend the memory the Jobs need to finish, and the logs become useless.
#
# Scaling them to zero first reproduces the order infra/README.md prescribes:
# migrate as its own step, then roll the tiers.
say "Holding the app tiers at zero until the Jobs finish"
kubectl -n "${NS}" scale deploy/ags-web deploy/ags-socketio \
  deploy/ags-worker-short deploy/ags-worker-default deploy/ags-worker-long \
  --replicas=0 >/dev/null 2>&1
kubectl -n "${NS}" scale statefulset/ags-scheduler --replicas=0 >/dev/null 2>&1

# ------------------------------------------------------------- datastores
say "Waiting for MariaDB and Redis"
kubectl -n "${NS}" rollout status deploy/mariadb --timeout=300s || die "mariadb never became ready"
kubectl -n "${NS}" rollout status deploy/redis-cache --timeout=120s || die "redis-cache failed"
kubectl -n "${NS}" rollout status deploy/redis-queue --timeout=120s || die "redis-queue failed"

# -------------------------------------------------------------- site init
say "Site init"
kubectl -n "${NS}" wait --for=condition=complete job/ags-site-init --timeout=1800s \
  || {
    echo "--- site-init logs ---" >&2
    kubectl -n "${NS}" logs job/ags-site-init --all-containers --tail=60 >&2
    die "site-init did not complete"
  }

# Recreate migrate now that the site exists.
#
# `kubectl apply -k` submits both Jobs together, so migrate starts racing
# site-init and loses: it fails with `404 Not Found: ags.localhost does not
# exist`, and with backoffLimit: 0 it does not retry — correctly, because a
# failed migration must be inspected rather than repeated blindly.
#
# This is the sequence 40-migrate-job-netpol.yaml documents for a real deploy:
# migrate is its own step, run after the thing it migrates exists.
say "Migrate"
kubectl -n "${NS}" delete job ags-migrate --ignore-not-found --wait=true >/dev/null 2>&1
kubectl apply -k "${REPO_ROOT}/infra/k8s-local" >/dev/null 2>&1 || die "could not recreate migrate"

kubectl -n "${NS}" wait --for=condition=complete job/ags-migrate --timeout=1800s \
  || {
    echo "--- migrate logs ---" >&2
    kubectl -n "${NS}" logs job/ags-migrate --all-containers --tail=60 >&2
    die "migrate did not complete"
  }

say "Rolling out the app tiers"
# One at a time. Six Frappe processes each importing the app tree simultaneously
# is the peak memory moment of the whole deploy, and on a small node it is the
# difference between a rollout and six OOMKills.
for r in deploy/ags-web deploy/ags-socketio deploy/ags-worker-short \
         deploy/ags-worker-default deploy/ags-worker-long; do
  kubectl -n "${NS}" scale "${r}" --replicas=1 >/dev/null
  kubectl -n "${NS}" rollout status "${r}" --timeout=600s || {
    kubectl -n "${NS}" describe "${r}" | tail -20 >&2
    die "${r} did not become ready"
  }
done
kubectl -n "${NS}" scale statefulset/ags-scheduler --replicas=1 >/dev/null
kubectl -n "${NS}" rollout status statefulset/ags-scheduler --timeout=600s \
  || die "scheduler did not become ready"

say "Cluster state"
kubectl -n "${NS}" get pods -o wide
echo
echo "   admin password: ${ADMIN_PASSWORD}"
echo "   port-forward:   kubectl -n ${NS} port-forward svc/ags-web 8000:8000"
echo "   verify:         sudo bash scripts/k8s-verify.sh"
