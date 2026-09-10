#!/usr/bin/env bash
# Make the ingress controller reachable on the port kind actually forwards.
#
#   sudo bash scripts/k8s-expose-ingress.sh
#
# kind-cluster.yaml maps container port 30080 to the host's 8080, which assumes
# the controller is exposed as a NodePort on 30080. The kind flavour of the
# ingress-nginx manifest instead binds hostPort 80/443 directly on the node, so
# the mapping points at a port nothing listens on and the host sees a refused
# connection with a controller that is running perfectly.
#
# Patching the Service is the cheap fix. The alternative is recreating the
# cluster with an 80 -> 8080 mapping, which means rebuilding the site.
set -uo pipefail
NS=ingress-nginx

kubectl -n "${NS}" patch svc ingress-nginx-controller \
  --type=json -p '[
    {"op":"replace","path":"/spec/type","value":"NodePort"},
    {"op":"replace","path":"/spec/ports/0/nodePort","value":30080}
  ]' >/dev/null 2>&1 || {
    echo "could not patch the controller service" >&2; exit 1; }

kubectl -n "${NS}" get svc ingress-nginx-controller \
  -o custom-columns=NAME:.metadata.name,TYPE:.spec.type,PORTS:.spec.ports[*].nodePort
