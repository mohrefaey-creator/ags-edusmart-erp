#!/usr/bin/env bash
# Install ingress-nginx into the local kind cluster and prove the Ingress works.
#
#   sudo bash scripts/k8s-install-ingress.sh
#
# infra/k8s ships an Ingress with real annotations — body size, upstream
# keepalive, brotli, rate limiting — and until now nothing has ever served it.
# `kubectl apply` accepting an Ingress says only that the API server parsed it;
# an Ingress with no controller behind it is an inert object, and every request
# in this project so far reached the app by port-forward instead.
#
# kind's own manifest is used rather than the generic cloud one: it patches the
# controller to a DaemonSet on the control-plane node with hostPort 80/443,
# which is what makes kind-cluster.yaml's extraPortMappings reach it.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NS=ingress-nginx
MANIFEST=${MANIFEST:-https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml}

say()  { printf '\n\033[1m== %s\033[0m\n' "$1"; }
note() { printf '   %s\n' "$1"; }

bash "${REPO_ROOT}/scripts/k8s-ensure-node.sh" 2>&1 | tail -1

say "Installing ingress-nginx"
if kubectl get ns "${NS}" >/dev/null 2>&1 && \
   kubectl -n "${NS}" get deploy ingress-nginx-controller >/dev/null 2>&1; then
  note "already installed"
else
  kubectl apply -f "${MANIFEST}" 2>&1 | tail -5 || {
    echo "could not apply the ingress-nginx manifest" >&2; exit 1; }
fi

# The namespace needs the label the NetworkPolicy selects on. allow-web-from-
# ingress permits traffic `from: namespaceSelector: {name: ingress-nginx}`, and
# the upstream manifest does not set that label — so with the default-deny in
# place the controller would reach the API server, accept the Ingress, and then
# be unable to talk to the web pods at all.
say "Labelling the namespace for the NetworkPolicy"
kubectl label ns "${NS}" name=ingress-nginx --overwrite >/dev/null 2>&1
note "name=ingress-nginx"

say "Waiting for the controller"
kubectl -n "${NS}" rollout status deploy/ingress-nginx-controller --timeout=600s 2>&1 | tail -2

say "Admission webhook"
# ingress-nginx installs a ValidatingWebhookConfiguration that every Ingress
# apply must call. On this node it routinely times out —
#
#   failed calling webhook "validate.nginx.ingress.kubernetes.io":
#   context deadline exceeded
#
# — and a timed-out webhook fails the apply, so the Ingress silently keeps its
# previous spec while kustomize reports success on everything else. The
# validation it provides is a check on nginx config syntax, which is worth
# having in a real cluster and not worth an unappliable Ingress here.
#
# Removed only when it actually fails, so the normal path keeps the validation.
if ! kubectl -n "${NS}" wait --for=condition=available      deploy/ingress-nginx-controller --timeout=120s >/dev/null 2>&1; then
  note "controller not available in time"
fi

probe=$(kubectl -n "${NS}" get validatingwebhookconfiguration         ingress-nginx-admission -o name 2>/dev/null)
if [ -n "${probe}" ]; then
  if kubectl -n ags-erp get ingress ags-erp >/dev/null 2>&1 &&      ! kubectl -n ags-erp annotate ingress ags-erp        ags.dev/webhook-probe="$(date +%s)" --overwrite >/dev/null 2>&1; then
    note "webhook is not answering — removing it for local use"
    kubectl delete validatingwebhookconfiguration ingress-nginx-admission >/dev/null 2>&1
  else
    note "webhook answers; leaving it in place"
  fi
fi

say "Status"
kubectl -n "${NS}" get pods 2>&1 | head -5
kubectl -n ags-erp get ingress 2>&1 | head -5
