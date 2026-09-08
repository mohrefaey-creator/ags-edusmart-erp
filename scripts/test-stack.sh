#!/usr/bin/env bash
# Run the ags_edusmart suite against a real site, in plain Docker.
#
#   sudo bash scripts/test-stack.sh            # reuse the site if it exists
#   sudo bash scripts/test-stack.sh --fresh    # rebuild the site from scratch
#   sudo bash scripts/test-stack.sh --down     # remove everything
#
# WHY NOT THE KUBERNETES CLUSTER
#
# Two reasons, and the second is the important one.
#
# The local cluster on this machine falls over every few minutes under memory
# pressure, and a test run that takes longer than the cluster stays up cannot
# produce a result. But more fundamentally: testing application logic does not
# need Kubernetes. The cluster proves the deployment topology; this proves the
# code. Keeping them apart means this can run in CI on any machine with Docker,
# which is where it belongs.
#
# WHY A DATABASE IS NOT OPTIONAL, EVEN FOR THE "UNIT" TESTS
#
# frappe's UnitTestCase sounds database-free and is not. flt(x, precision)
# rounds using the rounding method stored in System Settings, and reading that
# needs a database; without one, rounded() raises RuntimeError("object is not
# bound"), flt swallows it, and returns 0.0. Every money assertion then fails
# with amounts silently collapsed to zero, which reads exactly like a broken
# fee calculation. See scripts/check-flt-context.sh — that is a real trap, not
# a hypothetical.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG=${TAG:-ags/edusmart-erp:local}
NET=${NET:-ags-test-net}
DB=${DB:-ags-test-db}
REDIS=${REDIS:-ags-test-redis}
VOL=${VOL:-ags-test-sites}
SITE=${SITE:-test.localhost}
DB_ROOT_PASSWORD=${DB_ROOT_PASSWORD:-testroot}
ADMIN_PASSWORD=${ADMIN_PASSWORD:-testadmin}

say()  { printf '\n\033[1m== %s\033[0m\n' "$1"; }
note() { printf '   %s\n' "$1"; }

teardown() {
  docker rm -f "${DB}" "${REDIS}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
}

case "${1:-}" in
  --down)
    say "Removing the test stack"
    teardown
    docker volume rm "${VOL}" >/dev/null 2>&1 || true
    note "gone"
    exit 0 ;;
  --fresh)
    docker volume rm "${VOL}" >/dev/null 2>&1 || true ;;
esac

docker image inspect "${TAG}" >/dev/null 2>&1 || {
  echo "image ${TAG} not found — run scripts/build-image.sh" >&2; exit 1; }

say "Datastores"
docker network create "${NET}" >/dev/null 2>&1 || true
docker volume create "${VOL}" >/dev/null 2>&1 || true

docker rm -f "${DB}" "${REDIS}" >/dev/null 2>&1 || true

# Frappe requires utf8mb4 and a barracuda row format; the defaults in the
# official image are not what it expects and site creation fails late with a
# row-size error rather than early with a config one.
docker run -d --name "${DB}" --network "${NET}" \
  -e MARIADB_ROOT_PASSWORD="${DB_ROOT_PASSWORD}" \
  --health-cmd='healthcheck.sh --connect' --health-interval=5s \
  mariadb:11 \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci \
  --innodb-file-per-table=1 \
  --innodb-read-only-compressed=0 >/dev/null

docker run -d --name "${REDIS}" --network "${NET}" redis:7-alpine >/dev/null

note "waiting for MariaDB"
for _ in $(seq 1 60); do
  state=$(docker inspect -f '{{.State.Health.Status}}' "${DB}" 2>/dev/null || echo starting)
  [ "${state}" = healthy ] && break
  sleep 3
done
[ "${state:-}" = healthy ] || { echo "MariaDB never became healthy" >&2; docker logs --tail 20 "${DB}"; teardown; exit 1; }
note "MariaDB is healthy"

say "Site"
site_exists=$(docker run --rm -v "${VOL}:/home/frappe/frappe-bench/sites" \
  --entrypoint /bin/bash "${TAG}" -c "[ -f sites/${SITE}/site_config.json ] && echo yes || echo no" 2>/dev/null | tr -d '\r')

if [ "${site_exists}" = yes ]; then
  note "${SITE} already exists — reusing it (--fresh to rebuild)"
else
  note "creating ${SITE}; this installs six apps and takes a while"
  docker run --rm --network "${NET}" \
    -v "${VOL}:/home/frappe/frappe-bench/sites" \
    --entrypoint /bin/bash "${TAG}" -c "
      set -e
      cd /home/frappe/frappe-bench
      # No seeding step here, unlike the Kubernetes Job: Docker populates a
      # fresh named volume from the image's directory on first mount, so
      # apps.txt and the asset bundles are already there. A PVC does not do
      # that, which is why infra/k8s has an initContainer and this does not.
      bench set-config -g db_host '${DB}'
      bench set-config -g db_port 3306
      bench set-config -g redis_cache 'redis://${REDIS}:6379'
      bench set-config -g redis_queue 'redis://${REDIS}:6379'
      bench set-config -g redis_socketio 'redis://${REDIS}:6379'
      bench new-site '${SITE}' \
        --db-root-password '${DB_ROOT_PASSWORD}' \
        --admin-password '${ADMIN_PASSWORD}' \
        --no-mariadb-socket \
        --install-app erpnext --install-app payments --install-app hrms \
        --install-app education --install-app ags_edusmart
    " || { echo "site creation failed" >&2; teardown; exit 1; }
fi

say "Tests"
docker run --rm --network "${NET}" \
  -v "${VOL}:/home/frappe/frappe-bench/sites" \
  --entrypoint /bin/bash "${TAG}" -c "
    cd /home/frappe/frappe-bench
    bench --site '${SITE}' set-config allow_tests true >/dev/null 2>&1 || true
    bench --site '${SITE}' run-tests --app ags_edusmart
  "
rc=$?

say "Cleanup"
teardown
note "datastores removed; the site volume ${VOL} is kept for the next run"
exit ${rc}
