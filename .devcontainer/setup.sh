#!/usr/bin/env bash
# First-time setup inside the Codespace: get the image, create the site, start.
#
# Everything is logged to .devcontainer/setup.log. Watch it with:
#   tail -f .devcontainer/setup.log
#
# Idempotent. If the codespace is rebuilt, this runs again and skips whatever
# already exists.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
LOG=.devcontainer/setup.log
exec > >(tee -a "${LOG}") 2>&1

say() { printf '\n\033[1m== %s ==\033[0m  %s\n' "$1" "$(date -u +%H:%M:%S)"; }

COMPOSE_DIR=deploy/compose
# Any name works: Caddyfile.local rewrites the Host header upstream to this, so
# the forwarded github.dev URL — whatever it is — resolves to this site.
SITE_NAME=ags.codespace
IMAGE_TAG=${AGS_IMAGE_TAG:-sha-9aa8035e2658}
IMAGE=ghcr.io/mohrefaey-creator/ags-edusmart-erp:${IMAGE_TAG}

say "Docker"
for _ in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 2; done
docker info >/dev/null 2>&1 || { echo "docker never came up"; exit 1; }
docker --version; docker compose version

# ------------------------------------------------------------------ image
say "Image"
if docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "already present: ${IMAGE}"
else
  # The codespace's token can read packages published by this repository.
  # If the package is private and this login is refused, fall through to
  # building from source below.
  echo "${GITHUB_TOKEN:-}" | docker login ghcr.io -u "${GITHUB_USER:-x}" --password-stdin >/dev/null 2>&1 \
    && echo "logged in to ghcr.io" || echo "ghcr login not available; will try anonymous pull"
  if docker pull "${IMAGE}"; then
    echo "pulled ${IMAGE}"
  else
    say "Image pull failed — building from source (about 40 minutes)"
    # The app is a separate private repo; devcontainer.json asked for read
    # access to it at creation time.
    if [ ! -d apps/ags_edusmart/.git ]; then
      git clone "https://x-access-token:${GITHUB_TOKEN}@github.com/mohrefaey-creator/ags_edusmart.git" apps/ags_edusmart \
        || { echo "could not clone the app repo — accept the repository-access prompt when creating the codespace"; exit 1; }
    fi
    docker build -f infra/docker/Dockerfile -t ags/edusmart-erp:local . || { echo "build failed"; exit 1; }
    docker tag ags/edusmart-erp:local "${IMAGE}"
  fi
fi
docker logout ghcr.io >/dev/null 2>&1 || true

# -------------------------------------------------------------------- .env
say "Configuration"
cd "${COMPOSE_DIR}" || exit 1
if [ ! -f .env ]; then
  cp .env.example .env
  admin=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-16)
  dbroot=$(openssl rand -base64 30 | tr -d '/+=')
  sed -i "s|^SITE_NAME=.*|SITE_NAME=${SITE_NAME}|" .env
  sed -i "s|^ACME_EMAIL=.*|ACME_EMAIL=eval@example.invalid|" .env
  sed -i "s|^DB_ROOT_PASSWORD=.*|DB_ROOT_PASSWORD=${dbroot}|" .env
  sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=${admin}|" .env
  sed -i "s|^GUNICORN_WORKERS=.*|GUNICORN_WORKERS=3|" .env
  sed -i "s|^DB_BUFFER_POOL=.*|DB_BUFFER_POOL=512M|" .env
  sed -i "s|^AGS_IMAGE=.*|AGS_IMAGE=${IMAGE}|" .env
  echo "wrote .env (site ${SITE_NAME})"
else
  echo ".env already exists — keeping it"
fi
docker compose -f compose.yaml -f compose.local.yaml config >/dev/null || { echo "compose config invalid"; exit 1; }

# -------------------------------------------------------------- datastores
say "Datastores"
docker compose -f compose.yaml -f compose.local.yaml up -d mariadb redis-cache redis-queue
state=starting
for _ in $(seq 1 60); do
  state=$(docker compose ps mariadb --format '{{.Health}}' 2>/dev/null | head -1)
  [ "${state}" = healthy ] && break
  sleep 5
done
echo "mariadb: ${state}"
[ "${state}" = healthy ] || { docker compose logs --tail=30 mariadb; exit 1; }

# -------------------------------------------------------------------- site
say "Site — installs six apps, 15 to 30 minutes"
docker compose --profile setup -f compose.yaml -f compose.local.yaml run --rm site-init 2>&1 \
  | grep -vE 'Updating DocTypes|^[[:space:]]*$'
docker compose --profile setup -f compose.yaml -f compose.local.yaml run --rm migrate 2>&1 | tail -3

# ------------------------------------------------------------------- start
say "Application"
docker compose -f compose.yaml -f compose.local.yaml up -d
for _ in $(seq 1 40); do
  h=$(docker compose ps web --format '{{.Health}}' 2>/dev/null | head -1)
  [ "${h}" = healthy ] && break
  sleep 10
done
echo "web: ${h:-unknown}"
docker compose ps --format '  {{.Service}}\t{{.State}}'

# ------------------------------------------------------------ first-run
# Frappe holds every user at /desk/setup-wizard until it is completed, which
# makes a fresh site look like "login does nothing". Complete it here with the
# evaluation defaults so the first page a reviewer sees is the desk.
say "Setup wizard"
bash complete-setup.sh 2>&1 | tail -8

say "Ready"
echo "open the forwarded port 8080 (Ports panel) — or:"
echo "  https://${CODESPACE_NAME:-<codespace>}-8080.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}/login"
echo "login: Administrator / $(grep '^ADMIN_PASSWORD=' .env | cut -d= -f2)"
