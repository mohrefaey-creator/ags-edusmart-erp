#!/usr/bin/env bash
# Prove the Ingress actually serves the app, end to end.
#
#   sudo bash scripts/verify-ingress.sh
#
# Until this existed, every request in this project reached the app by
# port-forward, which bypasses the Ingress, the controller, its annotations and
# the allow-web-from-ingress NetworkPolicy entirely. `kubectl apply` accepting
# an Ingress proves only that the API server parsed it.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NS=${NS:-ags-erp}
SITE=${SITE:-ags.localhost}
INGRESS_NS=ingress-nginx

say()  { printf '\n\033[1m== %s\033[0m\n' "$1"; }
note() { printf '   %s\n' "$1"; }

bash "${REPO_ROOT}/scripts/k8s-ensure-node.sh" 2>&1 | tail -1
bash "${REPO_ROOT}/scripts/k8s-reap-stuck-pods.sh" >/dev/null 2>&1

say "Controller"
kubectl -n "${INGRESS_NS}" get pods --no-headers 2>&1 | head -3

say "Exposing the controller on the port kind forwards"
# kind-cluster.yaml maps container 30080 -> host 8080, which assumes a NodePort.
# The kind flavour of ingress-nginx binds hostPort 80 instead, so the mapping
# points at a port nothing listens on and the host sees a refused connection
# from a controller that is running perfectly.
kubectl -n "${INGRESS_NS}" patch svc ingress-nginx-controller --type=json -p \
  '[{"op":"replace","path":"/spec/type","value":"NodePort"},
    {"op":"replace","path":"/spec/ports/0/nodePort","value":30080}]' >/dev/null 2>&1 \
  && note "NodePort 30080" || note "could not patch (may already be set)"

say "Namespace label the NetworkPolicy selects on"
# allow-web-from-ingress permits `from: namespaceSelector: {name: ingress-nginx}`.
# The upstream manifest does not set that label, so with the default-deny in
# place the controller accepts the Ingress and then cannot reach the web pods.
kubectl label ns "${INGRESS_NS}" name=ingress-nginx --overwrite >/dev/null 2>&1
note "name=ingress-nginx"

say "Ingress object"
kubectl -n "${NS}" get ingress 2>&1 | head -3

say "Request through the ingress, from inside the node"
# From the node, not the Windows host: the host's view depends on kind's port
# mapping and WSL's localhost forwarding, and a failure there says nothing about
# whether the Ingress works.
for path in / /api/method/ping; do
  code=$(docker exec ags-erp-control-plane curl -s -o /dev/null -w '%{http_code}' \
         --max-time 15 -H "Host: ${SITE}" "http://localhost:30080${path}" 2>/dev/null)
  printf '   %-22s -> %s\n' "${path}" "${code:-no answer}"
done

say "Following the redirect: HTTPS through the ingress"
# The 308 above is not a failure. The Ingress declares tls:, so nginx redirects
# HTTP to HTTPS, which is what it should do. The question is whether anything
# answers on the other side. -k because the certificate here is whatever the
# controller falls back to; whether it is a *trusted* certificate is the next
# section's problem, not this one's.
for path in / /api/method/ping; do
  code=$(docker exec ags-erp-control-plane curl -sk -o /dev/null -w '%{http_code}'          --max-time 20 -H "Host: ${SITE}" "https://localhost:443${path}" 2>/dev/null)
  printf '   %-22s -> %s
' "${path}" "${code:-no answer}"
done

say "Which certificate is being served"
docker exec ags-erp-control-plane sh -c   "echo | openssl s_client -connect localhost:443 -servername ${SITE} 2>/dev/null    | openssl x509 -noout -subject -issuer -dates 2>/dev/null"   | sed 's/^/   /' || note "could not read the certificate"

say "Same request with the wrong Host (should not reach the app)"
code=$(docker exec ags-erp-control-plane curl -s -o /dev/null -w '%{http_code}' \
       --max-time 15 -H "Host: wrong.example" "http://localhost:30080/" 2>/dev/null)
note "wrong Host -> ${code:-no answer}"
