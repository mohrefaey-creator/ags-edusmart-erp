#!/usr/bin/env bash
# First-run site creation for the single-VM deployment.
#
#   docker compose --profile setup run --rm site-init
#
# A file rather than an inline `command:` in compose.yaml, because the shell in
# there has to survive YAML quoting and compose's own ${} interpolation at the
# same time — every $ needs doubling and a mistake shows up twenty minutes into
# app installation. This is idempotent and safe to re-run.
set -euo pipefail

cd /home/frappe/frappe-bench

# These live on the shared volume, so every container reads the same ones.
# bench init ran with --skip-redis-config-generation, so common_site_config
# carries no connection details until this writes them.
bench set-config -g db_host "${DB_HOST}"
bench set-config -g db_port "${DB_PORT}"
bench set-config -g redis_cache    "redis://${REDIS_CACHE_HOST}:${REDIS_CACHE_PORT}"
bench set-config -g redis_queue    "redis://${REDIS_QUEUE_HOST}:${REDIS_QUEUE_PORT}"
bench set-config -g redis_socketio "redis://${REDIS_SOCKETIO_HOST}:${REDIS_CACHE_PORT}"

# default_site lets the CLI and socketio resolve a site with no Host header.
# It does NOT make HTTP requests resolve — frappe applies that fallback when
# resolving a site by name, not when routing a request. The web tier depends on
# Caddy passing the real Host through, which it does.
bench set-config -g default_site "${SITE_NAME}"

if [ -f "sites/${SITE_NAME}/site_config.json" ]; then
  echo "[site-init] ${SITE_NAME} already exists"
else
  echo "[site-init] creating ${SITE_NAME}"
  # --mariadb-user-host-login-scope='%' replaces the deprecated
  # --no-mariadb-socket, which was always misnamed: it had nothing to do with
  # sockets, it sets the host scope of the granted database user.
  bench new-site "${SITE_NAME}" \
    --db-root-password "${DB_ROOT_PASSWORD}" \
    --admin-password "${ADMIN_PASSWORD}" \
    --mariadb-user-host-login-scope='%'
fi

# One app at a time, not five --install-app flags on new-site. Batched, the
# after_install hooks interleave and erpnext's company setup can run before its
# own fixtures land.
for app in erpnext payments hrms education ags_edusmart; do
  if bench --site "${SITE_NAME}" list-apps 2>/dev/null | grep -qx "${app}"; then
    echo "[site-init] ${app} already installed"
  else
    echo "[site-init] installing ${app}"
    bench --site "${SITE_NAME}" install-app "${app}"
  fi
done

echo "[site-init] done"
bench --site "${SITE_NAME}" list-apps
