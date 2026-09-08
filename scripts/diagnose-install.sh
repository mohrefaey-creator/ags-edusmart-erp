#!/usr/bin/env bash
# Find which app's install creates a Company, and whether erpnext's Warehouse
# Type records exist by the time it does.
#
#   sudo bash scripts/diagnose-install.sh
#
# Site creation dies on `LinkValidationError: Could not find Warehouse Type:
# Transit`. erpnext creates a "Goods In Transit" warehouse whenever a Company is
# saved, and that warehouse links to a Warehouse Type record. So either
# something creates a Company before erpnext's own fixtures land, or those
# fixtures never land at all. The error names neither.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG=${TAG:-ags/edusmart-erp:local}
NET=ags-diag-net
DB=ags-diag-db
REDIS=ags-diag-redis
VOL=ags-diag-sites
SITE=diag.localhost

cleanup() {
  docker rm -f "${DB}" "${REDIS}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker rm -f "${DB}" "${REDIS}" >/dev/null 2>&1 || true
docker volume rm "${VOL}" >/dev/null 2>&1 || true
docker network create "${NET}" >/dev/null 2>&1 || true
docker volume create "${VOL}" >/dev/null 2>&1 || true

docker run -d --name "${DB}" --network "${NET}" \
  -e MARIADB_ROOT_PASSWORD=diagroot \
  --health-cmd='healthcheck.sh --connect' --health-interval=5s \
  mariadb:11 --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci --innodb-file-per-table=1 \
  --innodb-read-only-compressed=0 >/dev/null
docker run -d --name "${REDIS}" --network "${NET}" redis:7-alpine >/dev/null

echo "waiting for MariaDB"
state=starting
for _ in $(seq 1 60); do
  state=$(docker inspect -f '{{.State.Health.Status}}' "${DB}" 2>/dev/null || echo starting)
  [ "${state}" = healthy ] && break
  sleep 3
done
[ "${state}" = healthy ] || { echo "MariaDB never healthy" >&2; exit 1; }

docker run --rm --network "${NET}" \
  -v "${VOL}:/home/frappe/frappe-bench/sites" \
  -v "${REPO_ROOT}/scripts:/opt/scripts:ro" \
  -e SITE="${SITE}" -e DB_HOST="${DB}" -e REDIS_HOST="${REDIS}" \
  -e DB_ROOT_PASSWORD=diagroot -e ADMIN_PASSWORD=diagadmin \
  --entrypoint /bin/bash "${TAG}" /opt/scripts/lib/diagnose-install.sh 2>&1 \
  | grep -vE 'Updating DocTypes|^[[:space:]]*$'

docker volume rm "${VOL}" >/dev/null 2>&1 || true
