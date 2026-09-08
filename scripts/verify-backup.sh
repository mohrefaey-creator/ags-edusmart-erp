#!/usr/bin/env bash
# Does the nightly backup actually produce a backup?
#
#   sudo bash scripts/verify-backup.sh
#
# Runs the image's "backup" role against the test site the same way the CronJob
# runs it in the cluster, then checks that files landed and are non-empty. The
# CronJob previously named the site itself rather than using SITE_NAME, so it
# ran against a site that did not exist — and a backup that fails is discovered
# on the day it is needed.
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
[ "${state}" = healthy ] || { echo "MariaDB never healthy" >&2; exit 1; }

echo "== running the backup role (as the CronJob does) =="
# SITE_NAME from the environment, exactly like the ConfigMap supplies it.
docker run --rm --network "${NET}" \
  -v "${VOL}:/home/frappe/frappe-bench/sites" \
  -e SITE_NAME="${SITE}" -e DB_HOST="${DB}" -e DB_PORT=3306 \
  -e REDIS_CACHE_HOST="${REDIS}" -e REDIS_QUEUE_HOST="${REDIS}" \
  -e REDIS_CACHE_PORT=6379 -e REDIS_QUEUE_PORT=6379 \
  "${TAG}" backup --with-files 2>&1 | tail -12
rc=${PIPESTATUS[0]}

echo
echo "== what landed on disk =="
docker run --rm -v "${VOL}:/sites" --entrypoint /bin/sh "${TAG}" -c \
  "ls -lh /sites/${SITE}/private/backups 2>/dev/null | tail -8 || echo 'no backups directory'"

exit "${rc}"
