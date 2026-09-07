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
    # gunicorn must run from sites/, not from the bench root.
    #
    # Frappe resolves its sites path relative to the working directory, and
    # bench's own supervisor config runs this exact command with
    # `directory=<bench>/sites`. Started from the bench root instead, Frappe
    # initialises with no sites, builds an empty URL map, and answers *every*
    # request — /, /app, /api/method/ping — with Werkzeug's 404. Not Frappe's
    # "site does not exist" page: Werkzeug's, because as far as the router is
    # concerned no route was ever registered.
    #
    # gunicorn is up, healthy, logging access lines, and serving 404 to
    # everything. The startup probe fails, the kubelet restarts the pod, and
    # the loop looks like a probe problem rather than a one-word cwd bug.
    cd "${BENCH_DIR}/sites"
    exec gunicorn \
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
    exec bench worker --queue "${QUEUE}"
    ;;

  scheduler)
    # Guard rail, not a substitute for replicas: 1. Two schedulers double every
    # scheduled job, which for the reminder ladder means two SMS per parent.
    log "starting scheduler (this must be the ONLY scheduler in the cluster)"
    exec bench schedule
    ;;

  socketio)
    exec node apps/frappe/socketio.js
    ;;

  migrate)
    # Run as a Job before rolling the web tier, never from an app container:
    # concurrent migrations on one site corrupt the schema.
    log "migrating ${SITE}"
    exec bench --site "${SITE}" migrate
    ;;

  bench)
    shift
    exec bench "$@"
    ;;

  *)
    exec "$@"
    ;;
esac
