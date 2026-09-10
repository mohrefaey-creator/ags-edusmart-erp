#!/usr/bin/env bash
# Why are the workers and socketio losing their Redis connections?
#
#   sudo bash scripts/compose-redis-probe.sh
#
# Both roles connect successfully and are then dropped — "Broken pipe" from the
# python client, "Socket closed unexpectedly" from node. A connection that is
# accepted and then closed is a different problem from one that is refused, and
# the usual cause is Redis rejecting the client after the handshake rather than
# the network failing.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}/deploy/compose" || exit 1

for pair in "redis-cache 13000" "redis-queue 11000"; do
  set -- ${pair}
  host=$1 port=$2
  printf '\n\033[1m== %s:%s ==\033[0m\n' "${host}" "${port}"

  echo "-- PING from another container on the same network --"
  docker compose exec -T "${host}" redis-cli -p "${port}" PING 2>&1 | head -3

  echo "-- what the server thinks it is --"
  docker compose exec -T "${host}" redis-cli -p "${port}" CONFIG GET protected-mode 2>&1 | head -3
  docker compose exec -T "${host}" redis-cli -p "${port}" CONFIG GET maxmemory 2>&1 | head -3
  docker compose exec -T "${host}" redis-cli -p "${port}" CONFIG GET timeout 2>&1 | head -3

  echo "-- reachable from the web container? --"
  docker compose exec -T web sh -c \
    "python -c \"
import socket,sys
s=socket.create_connection(('${host}',${port}),5)
s.sendall(b'PING\r\n')
print(repr(s.recv(64)))
s.close()
\"" 2>&1 | head -5

  echo "-- rejected clients / evictions --"
  docker compose exec -T "${host}" redis-cli -p "${port}" INFO stats 2>&1 \
    | grep -E 'rejected_connections|evicted_keys|expired_keys' | head -3
  docker compose exec -T "${host}" redis-cli -p "${port}" INFO clients 2>&1 \
    | grep -E 'connected_clients|maxclients' | head -3
done
