#!/usr/bin/env bash
# Prepare a fresh Ubuntu VM to run the single-VM deployment.
#
#   curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/scripts/vm-bootstrap.sh | sudo bash
#   — or, after cloning —
#   sudo bash scripts/vm-bootstrap.sh
#
# Idempotent: safe to re-run. Does exactly four things and nothing clever:
#
#   1. installs Docker Engine and the compose plugin from Docker's own apt repo
#      (Ubuntu's packaged docker.io is old and ships without compose v2)
#   2. opens 22, 80 and 443 in ufw and closes everything else
#   3. turns on unattended security upgrades for the OS
#   4. adds the invoking user to the docker group
#
# It does NOT deploy the application. deploy/compose/DEPLOY.md is the runbook;
# this is step 2 of it.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }

say() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

say "OS"
. /etc/os-release
echo "   ${PRETTY_NAME}"
case "${ID}" in
  ubuntu|debian) ;;
  *) echo "this script targets Ubuntu/Debian; adapt the Docker install for ${ID}" >&2; exit 1 ;;
esac

say "Docker Engine + compose plugin"
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "   already installed: $(docker --version | cut -d, -f1), $(docker compose version | cut -d' ' -f4)"
else
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg >/dev/null
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin >/dev/null
  systemctl enable --now docker
  echo "   installed: $(docker --version | cut -d, -f1), $(docker compose version | cut -d' ' -f4)"
fi

say "Docker log rotation"
# Without this, container logs grow until the disk is full, and the first
# symptom is the application unable to write attachments.
if [ ! -f /etc/docker/daemon.json ]; then
  cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "50m", "max-file": "5" }
}
JSON
  systemctl restart docker
  echo "   configured: 50 MB x 5 per container"
else
  echo "   /etc/docker/daemon.json already exists — left alone"
fi

say "Firewall"
apt-get install -y -qq ufw >/dev/null
ufw --force default deny incoming >/dev/null
ufw --force default allow outgoing >/dev/null
ufw allow 22/tcp  >/dev/null   # ssh
ufw allow 80/tcp  >/dev/null   # ACME challenge + redirect to https
ufw allow 443/tcp >/dev/null   # the application
ufw allow 443/udp >/dev/null   # HTTP/3
ufw --force enable >/dev/null
ufw status | sed 's/^/   /'

say "Unattended OS security upgrades"
apt-get install -y -qq unattended-upgrades >/dev/null
dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null 2>&1 || true
echo "   enabled (OS packages only; the application image is upgraded deliberately)"

say "docker group"
target=${SUDO_USER:-}
if [ -n "${target}" ] && [ "${target}" != root ]; then
  usermod -aG docker "${target}"
  echo "   ${target} added — log out and back in for it to apply"
else
  echo "   no non-root invoking user; skipped"
fi

say "Done"
echo "   next: deploy/compose/DEPLOY.md, step 3"
