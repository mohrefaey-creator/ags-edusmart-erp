#!/usr/bin/env bash
# Run the ags_edusmart suite against a real site, in plain Docker.
#
#   sudo bash scripts/test-stack.sh            # reuse the site if it exists
#   sudo bash scripts/test-stack.sh --fresh    # rebuild the site from scratch
#   sudo bash scripts/test-stack.sh --down     # remove everything
#
# WHY NOT THE KUBERNETES CLUSTER
#
# The local cluster on this machine falls over more often than a full run takes,
# so a run longer than the cluster's uptime cannot produce a result. But the
# better reason: testing application logic does not need Kubernetes. The cluster
# proves the deployment topology; this proves the code. Split, this runs
# anywhere Docker does, CI included.
#
# WHY A DATABASE IS NOT OPTIONAL, EVEN FOR THE "UNIT" TESTS
#
# frappe's UnitTestCase sounds database-free and is not. flt(x, precision)
# rounds using the method in System Settings, and reading that needs a database;
# without one rounded() raises RuntimeError("object is not bound"), flt swallows
# it and returns 0.0. Every money assertion then fails with amounts silently
# collapsed to zero, which reads exactly like a broken fee engine. Measured in
# scripts/check-flt-context.sh.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG=${TAG:-ags/edusmart-erp:local}
NET=${NET:-ags-test-net}
DB=${DB:-ags-test-db}
REDIS=${REDIS:-ags-test-redis}
VOL=${VOL:-ags-test-sites}
# The database needs a volume too. Without one the site files survive a run and
# the database they point at does not, so the next run authenticates as a user
# that no longer exists and dies on "Access denied" — a broken reuse that reads
# as a credentials bug.
DBVOL=${DBVOL:-ags-test-db-data}
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
    docker volume rm "${VOL}" "${DBVOL}" >/dev/null 2>&1 || true
    note "gone"
    exit 0 ;;
  --fresh)
    # Loud, not `|| true`. Swallowing this failure makes --fresh silently reuse
    # the old volume, and a half-installed site from a previous failed run then
    # fails again in a way that looks like a bug in the apps: the first run here
    # died partway through erpnext, and every later --fresh re-ran against that
    # wreckage and reported the same LinkValidationError. The flag has to mean
    # what it says or it is worse than not existing.
    docker rm -f "${DB}" "${REDIS}" >/dev/null 2>&1 || true
    # Both volumes together: dropping the site without the database (or the
    # reverse) leaves the two disagreeing about which site exists, and the next
    # run authenticates as a database user that no longer exists.
    for v in "${VOL}" "${DBVOL}"; do
      if docker volume inspect "${v}" >/dev/null 2>&1; then
        docker volume rm "${v}" >/dev/null 2>&1 || {
          echo "--fresh could not remove volume ${v}; something still holds it:" >&2
          docker ps -a --filter "volume=${v}" --format '  {{.Names}} ({{.Status}})' >&2
          exit 1
        }
      fi
      docker volume inspect "${v}" >/dev/null 2>&1 && {
        echo "--fresh: volume ${v} still exists after removal" >&2; exit 1; }
    done
    ;;
esac

docker image inspect "${TAG}" >/dev/null 2>&1 || {
  echo "image ${TAG} not found — run scripts/build-image.sh" >&2; exit 1; }

say "Datastores"
docker network create "${NET}" >/dev/null 2>&1 || true
docker volume create "${VOL}" >/dev/null 2>&1 || true
docker volume create "${DBVOL}" >/dev/null 2>&1 || true
docker rm -f "${DB}" "${REDIS}" >/dev/null 2>&1 || true

# utf8mb4 and per-table innodb: frappe needs both, and the image defaults fail
# late with a row-size error rather than early with a config one.
docker run -d --name "${DB}" --network "${NET}" \
  -e MARIADB_ROOT_PASSWORD="${DB_ROOT_PASSWORD}" \
  -v "${DBVOL}:/var/lib/mysql" \
  --health-cmd='healthcheck.sh --connect' --health-interval=5s \
  mariadb:11 \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci \
  --innodb-file-per-table=1 \
  --innodb-read-only-compressed=0 >/dev/null || exit 1

docker run -d --name "${REDIS}" --network "${NET}" redis:7-alpine >/dev/null || exit 1

note "waiting for MariaDB"
state=starting
for _ in $(seq 1 60); do
  state=$(docker inspect -f '{{.State.Health.Status}}' "${DB}" 2>/dev/null || echo starting)
  [ "${state}" = healthy ] && break
  sleep 3
done
[ "${state}" = healthy ] || { echo "MariaDB never became healthy" >&2; docker logs --tail 20 "${DB}"; teardown; exit 1; }
note "MariaDB is healthy"

# The container runs mounted script FILES, not strings. The embedded version had
# to survive the host shell, the WSL shell and the container shell, and died on
# `syntax error: unexpected end of file` twenty minutes into app installation.
common_mounts=(
  -v "${VOL}:/home/frappe/frappe-bench/sites"
  -v "${REPO_ROOT}/scripts:/opt/scripts:ro"
  # The working tree's app, over the copy baked into the image. Without this,
  # testing a one-line change to ags_edusmart means a 40-minute image rebuild.
  # The image pip-installs the app in editable mode at exactly this path, so the
  # mount is picked up with no reinstall. Read-write because Python writes
  # __pycache__ into it.
  -v "${REPO_ROOT}/apps/ags_edusmart:/home/frappe/frappe-bench/apps/ags_edusmart"
)

say "Site"
docker run --rm --network "${NET}" "${common_mounts[@]}" \
  -e SITE="${SITE}" -e DB_HOST="${DB}" -e REDIS_HOST="${REDIS}" \
  -e DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD}" -e ADMIN_PASSWORD="${ADMIN_PASSWORD}" \
  --entrypoint /bin/bash "${TAG}" /opt/scripts/lib/test-site-init.sh \
  2>&1 | grep -vE 'Updating DocTypes|^[[:space:]]*$'
site_rc=${PIPESTATUS[0]}
if [ "${site_rc}" -ne 0 ]; then
  echo "site setup failed (exit ${site_rc})" >&2
  teardown
  exit 1
fi

say "Tests"
docker run --rm --network "${NET}" "${common_mounts[@]}" \
  -e SITE="${SITE}" \
  --entrypoint /bin/bash "${TAG}" /opt/scripts/lib/test-run.sh
rc=$?

say "Cleanup"
teardown
note "datastores removed; the site volume ${VOL} is kept for the next run"
exit ${rc}
