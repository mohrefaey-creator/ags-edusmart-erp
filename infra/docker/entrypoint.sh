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
#
# The Redis ports are configurable and default to the odd values bench's own
# config generator picks. They were hardcoded, which is fine for the Redis
# deployed alongside this and wrong for every managed one: ElastiCache, Azure
# Cache and Redis Cloud all serve 6379. Against a correctly configured managed
# Redis the app would have been fine and the entrypoint would have refused to
# start it, reporting the datastore unreachable at a port nothing was listening
# on. Set REDIS_CACHE_PORT / REDIS_QUEUE_PORT to match the URLs in the site
# config.
wait_for "${DB_HOST:-mariadb}" "${DB_PORT:-3306}" "MariaDB"
wait_for "${REDIS_CACHE_HOST:-redis-cache}" "${REDIS_CACHE_PORT:-13000}" "redis-cache"
wait_for "${REDIS_QUEUE_HOST:-redis-queue}" "${REDIS_QUEUE_PORT:-11000}" "redis-queue"

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
    # First, any symlinks still under sites/assets on the volume become real
    # copies. The image builds its assets that way now, but a volume seeded
    # from an older image still holds links into an apps tree only the app
    # container has — and the proxy serving /assets from that volume then
    # 404s every stylesheet. Idempotent: nothing to do once no links remain.
    if [ -d sites/assets ]; then
      links=$(find sites/assets -maxdepth 1 -type l 2>/dev/null)
      if [ -n "${links}" ]; then
        log "materialising asset symlinks on the volume"
        for l in ${links}; do t=$(readlink -f "$l"); rm "$l"; cp -r "$t" "$l"; done
      fi
    fi
    log "migrating ${SITE}"
    exec bench --site "${SITE}" migrate
    ;;

  backup)
    # A role, not a bare `bench backup` in the CronJob's args, so the site name
    # comes from SITE_NAME like every other role's does. The CronJob used to
    # name the site itself, which meant the production site name was written in
    # two places and the nightly backup failed anywhere it disagreed — on the
    # local cluster it ran against erp.ags.edu.sa, which does not exist there.
    # A backup that fails is discovered when it is needed.
    log "backing up ${SITE}"
    # shift drops the role word, exactly as the bench) case does; without it
    # "backup" is passed on as an argument too and bench rejects the duplicate.
    shift
    exec bench --site "${SITE}" backup "$@"
    ;;

  bench)
    shift
    exec bench "$@"
    ;;

  *)
    exec "$@"
    ;;
esac
