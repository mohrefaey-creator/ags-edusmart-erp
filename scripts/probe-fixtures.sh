#!/usr/bin/env bash
# Inspect the test site: did the upstream-fixture guard actually run?
#
#   sudo bash scripts/probe-fixtures.sh
#
# Uses the same volumes as scripts/test-stack.sh, so it looks at the site that
# run actually built. Pointing it at a fresh database instead just produces
# "Access denied" for a user that only exists in the other one.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG=${TAG:-ags/edusmart-erp:local}
NET=${NET:-ags-test-net}
DB=${DB:-ags-test-db}
REDIS=${REDIS:-ags-test-redis}
VOL=${VOL:-ags-test-sites}
DBVOL=${DBVOL:-ags-test-db-data}
SITE=${SITE:-test.localhost}
DB_ROOT_PASSWORD=${DB_ROOT_PASSWORD:-testroot}

cleanup() {
  docker rm -f "${DB}" "${REDIS}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create "${NET}" >/dev/null 2>&1 || true
docker rm -f "${DB}" "${REDIS}" >/dev/null 2>&1 || true

docker run -d --name "${DB}" --network "${NET}" \
  -e MARIADB_ROOT_PASSWORD="${DB_ROOT_PASSWORD}" \
  -v "${DBVOL}:/var/lib/mysql" \
  --health-cmd='healthcheck.sh --connect' --health-interval=5s \
  mariadb:11 --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci --innodb-file-per-table=1 \
  --innodb-read-only-compressed=0 >/dev/null
docker run -d --name "${REDIS}" --network "${NET}" redis:7-alpine >/dev/null

state=starting
for _ in $(seq 1 60); do
  state=$(docker inspect -f '{{.State.Health.Status}}' "${DB}" 2>/dev/null || echo starting)
  [ "${state}" = healthy ] && break
  sleep 3
done
echo "mariadb: ${state}"

docker run --rm --network "${NET}" \
  -v "${VOL}:/home/frappe/frappe-bench/sites" \
  -v "${REPO_ROOT}/scripts:/opt/scripts:ro" \
  -v "${REPO_ROOT}/apps/ags_edusmart:/home/frappe/frappe-bench/apps/ags_edusmart" \
  -e SITE="${SITE}" \
  --entrypoint /bin/bash "${TAG}" /opt/scripts/lib/probe-fixtures.sh
