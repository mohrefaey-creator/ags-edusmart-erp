#!/usr/bin/env bash
# Make sure the kind node is running and its API server answers.
#
#   sudo bash scripts/k8s-ensure-node.sh
#
# kind creates its node with `--restart=on-failure:1`, which means that once
# the Docker daemon is restarted — routine on WSL, where the VM is stopped
# whenever the host decides it is idle — the node stays down. Everything
# downstream then fails with a message about whatever touched it first:
# `docker exec ... is not running`, or `The connection to the server was
# refused`, neither of which names the cause.
#
# Sourcing this, or running it, makes that self-healing. It also switches the
# node to `unless-stopped` so the next daemon restart brings it back on its own.
set -uo pipefail

CLUSTER=${CLUSTER:-ags-erp}
NODE=${NODE:-${CLUSTER}-control-plane}
TRIES=${TRIES:-40}

docker inspect "${NODE}" >/dev/null 2>&1 || {
  echo "no such node ${NODE} — create the cluster first" >&2; exit 1; }

if [ "$(docker inspect -f '{{.State.Running}}' "${NODE}")" != "true" ]; then
  echo "   ${NODE} was stopped — starting it"
  docker start "${NODE}" >/dev/null || { echo "could not start ${NODE}" >&2; exit 1; }
fi

# Survive the next daemon restart without hand-holding.
docker update --restart=unless-stopped "${NODE}" >/dev/null 2>&1 || true

# Running is not the same as serving: etcd and the apiserver take a while.
for _ in $(seq 1 "${TRIES}"); do
  if kubectl get --raw='/readyz' >/dev/null 2>&1; then
    echo "   API server is ready"
    exit 0
  fi
  sleep 3
done

echo "API server did not become ready" >&2
docker logs "${NODE}" 2>&1 | tail -15 >&2
exit 1
