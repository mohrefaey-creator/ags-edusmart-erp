#!/usr/bin/env bash
# Local image registry for the kind cluster, and push the app image to it.
#
#   sudo bash scripts/k8s-local-registry.sh
#
# Exists because `kind load docker-image` saves the whole image to a tar and
# imports it in one go. For a 4.35 GB artefact inside a 4 GB WSL VM that did not
# fail gracefully — it took the VM down. A registry push streams compressed
# layers to disk instead, and the node then performs a genuine image pull, which
# also means imagePullPolicy and the manifests' image reference are exercised
# rather than bypassed.
#
# Follows the kind local-registry recipe: a registry container on the kind
# network, plus a hosts.toml in each node's /etc/containerd/certs.d so that
# `localhost:5000` resolves to it from inside the cluster.
set -uo pipefail

CLUSTER=${CLUSTER:-ags-erp}
REG_NAME=${REG_NAME:-kind-registry}
REG_PORT=${REG_PORT:-5000}
IMAGE=${IMAGE:-ags/edusmart-erp:local}
TARGET="localhost:${REG_PORT}/${IMAGE}"

say() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
die() { printf '\033[31mFATAL: %s\033[0m\n' "$1" >&2; exit 1; }

docker image inspect "${IMAGE}" >/dev/null 2>&1 || die "${IMAGE} not built"

say "Registry"
if [ "$(docker inspect -f '{{.State.Running}}' "${REG_NAME}" 2>/dev/null)" = "true" ]; then
  echo "   ${REG_NAME} already running"
else
  docker rm -f "${REG_NAME}" >/dev/null 2>&1
  docker run -d --restart=always -p "127.0.0.1:${REG_PORT}:5000" \
    --name "${REG_NAME}" registry:2 >/dev/null || die "could not start registry"
  echo "   started ${REG_NAME}"
fi

# The registry must be on the kind network for the node to reach it by name.
if ! docker network inspect kind -f '{{range .Containers}}{{.Name}} {{end}}' 2>/dev/null \
     | grep -q "${REG_NAME}"; then
  docker network connect kind "${REG_NAME}" 2>/dev/null \
    && echo "   connected ${REG_NAME} to the kind network"
fi

# The node must be running to be configured, and on WSL it may not be.
bash "$(dirname "${BASH_SOURCE[0]}")/k8s-ensure-node.sh" || die "node not available"

say "Teaching each node where localhost:${REG_PORT} lives"
for node in $(kind get nodes --name "${CLUSTER}" 2>/dev/null); do
  dir="/etc/containerd/certs.d/localhost:${REG_PORT}"
  docker exec "${node}" mkdir -p "${dir}" || die "could not write to ${node}"
  # The node reaches the registry by container name on the kind network; the
  # name `localhost:5000` is only how the image is *referenced*.
  docker exec -i "${node}" cp /dev/stdin "${dir}/hosts.toml" <<EOF
[host."http://${REG_NAME}:5000"]
  capabilities = ["pull", "resolve"]
EOF
  echo "   ${node}"
done

say "Pushing ${IMAGE}"
docker tag "${IMAGE}" "${TARGET}" || die "tag failed"
docker push "${TARGET}" || die "push failed"

say "Done"
echo "   manifests should reference: ${TARGET}"
