#!/usr/bin/env bash
# Show why compose services are unhealthy or restarting.
#
#   sudo bash scripts/compose-logs.sh [service ...]
#
# `docker compose ps` says "restarting" and nothing else. This pulls the tail of
# each service's log, which is where the reason is.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}/deploy/compose" || exit 1

services=("$@")
if [ "${#services[@]}" -eq 0 ]; then
  services=(socketio worker-short redis-queue caddy)
fi

for svc in "${services[@]}"; do
  printf '\n\033[1m== %s ==\033[0m\n' "${svc}"
  printf '   state: %s\n\n' "$(docker compose ps "${svc}" --format '{{.State}} {{.Status}}' 2>/dev/null | head -1)"
  docker compose logs --tail=25 --no-log-prefix "${svc}" 2>&1 | tail -25
done
