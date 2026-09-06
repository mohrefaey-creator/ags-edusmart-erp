#!/usr/bin/env bash
# One image, several roles. The role is the container command, so web nodes,
# workers, the scheduler and socketio all ship the identical artefact - which is
# what makes "it works on the web node" mean anything for the worker.
set -euo pipefail

BENCH_DIR=${BENCH_DIR:-/home/frappe/frappe-bench}
SITE=${SITE_NAME:-ags.localhost}
cd "${BENCH_DIR}"

log() { printf '[entrypoint] %s\n' "$*" >&2; }

wait_for() {
  local host=$1 port=$2 label=$3 tries=${4:-60}
  for _ in $(seq 1 "${tries}"); do
    if (echo > "/dev/tcp/${host}/${port}") >/dev/null 2>&1; then
      log "${label} is up at ${host}:${port}"
      return 0
    fi
    sleep 2
  done
  log "FATAL: ${label} not reachable at ${host}:${port}"
  return 1
}

# Every role needs the database and Redis; failing fast here gives a readable
# error instead of a Frappe traceback 40 lines deep.
wait_for "${DB_HOST:-mariadb}" "${DB_PORT:-3306}" "MariaDB"
wait_for "${REDIS_CACHE_HOST:-redis-cache}" 13000 "redis-cache"
wait_for "${REDIS_QUEUE_HOST:-redis-queue}" 11000 "redis-queue"

case "${1:-web}" in
  web)
    WORKERS=${GUNICORN_WORKERS:-17}
    log "starting gunicorn with ${WORKERS} workers"
    exec env/bin/gunicorn \
      --bind 0.0.0.0:8000 \
      --workers "${WORKERS}" \
      --threads 1 \
      --worker-class sync \
      --timeout 120 \
      --graceful-timeout 30 \
      --max-requests 5000 \
      --max-requests-jitter 500 \
      --keep-alive 5 \
      --preload \
      --access-logfile - \
      --error-logfile - \
      frappe.app:application
    ;;

  worker)
    QUEUE=${WORKER_QUEUE:-default}
    log "starting worker on queue ${QUEUE}"
    exec env/bin/bench worker --queue "${QUEUE}"
    ;;

  scheduler)
    # Guard rail, not a substitute for replicas: 1. Two schedulers double every
    # scheduled job, which for the reminder ladder means two SMS per parent.
    log "starting scheduler (this must be the ONLY scheduler in the cluster)"
    exec env/bin/bench schedule
    ;;

  socketio)
    exec node apps/frappe/socketio.js
    ;;

  migrate)
    # Run as a Job before rolling the web tier, never from an app container:
    # concurrent migrations on one site corrupt the schema.
    log "migrating ${SITE}"
    exec env/bin/bench --site "${SITE}" migrate
    ;;

  bench)
    shift
    exec env/bin/bench "$@"
    ;;

  *)
    exec "$@"
    ;;
esac
