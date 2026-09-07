#!/usr/bin/env bash
# Install kubectl and kind for exercising infra/k8s locally.
#
#   sudo bash scripts/install-k8s-tools.sh
#
# kind rather than minikube or k3d: it runs the cluster inside the Docker
# daemon that already built the image, so `kind load docker-image` moves the
# 4.35 GB artefact without a registry.
#
# Both are pinned. An unpinned `latest` download makes a green run
# unreproducible, which is the whole point of exercising the manifests.
set -uo pipefail

KUBECTL_VERSION=${KUBECTL_VERSION:-v1.34.1}
KIND_VERSION=${KIND_VERSION:-v0.30.0}
ARCH=${ARCH:-amd64}
BIN=${BIN:-/usr/local/bin}

need_root() {
  [ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
}
need_root

fetch() {  # url dest
  curl -fsSL --retry 3 --retry-delay 2 -o "$2" "$1" || {
    echo "download failed: $1" >&2; return 1; }
}

if command -v kubectl >/dev/null 2>&1; then
  echo "kubectl already present: $(kubectl version --client -o yaml 2>/dev/null | grep gitVersion | head -1)"
else
  echo "installing kubectl ${KUBECTL_VERSION}"
  fetch "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${ARCH}/kubectl" \
        "${BIN}/kubectl" || exit 1
  chmod +x "${BIN}/kubectl"
fi

if command -v kind >/dev/null 2>&1; then
  echo "kind already present: $(kind version 2>/dev/null)"
else
  echo "installing kind ${KIND_VERSION}"
  fetch "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-${ARCH}" \
        "${BIN}/kind" || exit 1
  chmod +x "${BIN}/kind"
fi

echo
kubectl version --client 2>/dev/null | head -2
kind version
