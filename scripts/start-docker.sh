#!/usr/bin/env bash
# Bring the Docker daemon up inside WSL.
#
# WSL2 does not always run systemd as PID 1, and even when it does the docker
# unit is often not enabled, so `systemctl start docker` cannot be relied on.
# This handles both, and is idempotent.
#
#   sudo bash scripts/start-docker.sh
set -uo pipefail

if docker info >/dev/null 2>&1; then
  echo "docker already running"
else
  if [ "$(ps -p 1 -o comm=)" = "systemd" ]; then
    echo "starting via systemd"
    systemctl start docker >/dev/null 2>&1 || true
  fi

  if ! docker info >/dev/null 2>&1; then
    echo "starting dockerd directly"
    # WSL has no firewalld and an empty iptables ruleset; letting Docker manage
    # iptables is what gives containers outbound DNS and network access.
    nohup dockerd --iptables=true --ip6tables=false \
      >/var/log/dockerd.log 2>&1 &
  fi

  for _ in $(seq 1 45); do
    docker info >/dev/null 2>&1 && break
    sleep 2
  done
fi

if ! docker info >/dev/null 2>&1; then
  echo "FAILED to start docker. Last lines of /var/log/dockerd.log:" >&2
  tail -20 /var/log/dockerd.log >&2 2>/dev/null
  exit 1
fi

docker version --format 'client {{.Client.Version}} / server {{.Server.Version}}'
docker info --format 'storage {{.Driver}} | cgroup v{{.CgroupVersion}} | cpus {{.NCPU}} | mem {{.MemTotal}}'
