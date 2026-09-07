#!/usr/bin/env bash
# Watch the kind node's liveness, unattended.
#
#   sudo bash scripts/k8s-node-watch.sh [seconds]
#
# The node container has exited twice mid-deploy with code 128 and
# OOMKilled=false, which is neither a crash nor a kernel OOM. This establishes
# whether it dies on its own or only when something else touches it, before any
# more time goes into theories.
set -uo pipefail

NODE=${NODE:-ags-erp-control-plane}
SECONDS_TOTAL=${1:-150}
STEP=${STEP:-15}

docker start "${NODE}" >/dev/null 2>&1 || true

elapsed=0
while [ "${elapsed}" -lt "${SECONDS_TOTAL}" ]; do
  sleep "${STEP}"
  elapsed=$((elapsed + STEP))
  status=$(docker inspect "${NODE}" --format '{{.State.Status}}')
  code=$(docker inspect "${NODE}" --format '{{.State.ExitCode}}')
  mem=$(free -m | sed -n 2p | awk '{print $7"MB avail"}')
  printf '%4ss  %-10s exit=%-4s %s\n' "${elapsed}" "${status}" "${code}" "${mem}"
  [ "${status}" = "running" ] || break
done

echo
echo "--- last 20 lines of node log ---"
docker logs "${NODE}" 2>&1 | tail -20
