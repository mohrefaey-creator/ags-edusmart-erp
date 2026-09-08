#!/usr/bin/env bash
# Runs INSIDE the container. Creates the test site and installs the apps.
#
# A file rather than a string passed to `docker run ... bash -c "..."`, because
# that string had to survive the host shell, the WSL shell, and the container
# shell, and a for-loop in it died with "syntax error: unexpected end of file"
# after twenty minutes of app installation. Shell nested three deep is not worth
# debugging when a mounted file works.
#
# Expects: SITE, DB_HOST, REDIS_HOST, DB_ROOT_PASSWORD, ADMIN_PASSWORD
set -euo pipefail

cd /home/frappe/frappe-bench

bench set-config -g db_host "${DB_HOST}"
bench set-config -g db_port 3306
bench set-config -g redis_cache "redis://${REDIS_HOST}:6379"
bench set-config -g redis_queue "redis://${REDIS_HOST}:6379"
bench set-config -g redis_socketio "redis://${REDIS_HOST}:6379"

if [ -f "sites/${SITE}/site_config.json" ]; then
  echo "[test-site-init] ${SITE} already exists"
else
  echo "[test-site-init] creating ${SITE}"
  # --mariadb-user-host-login-scope='%' replaces --no-mariadb-socket, which
  # frappe now warns is deprecated and was always misnamed: it had nothing to
  # do with sockets, it controls the host scope of the granted user.
  bench new-site "${SITE}" \
    --db-root-password "${DB_ROOT_PASSWORD}" \
    --admin-password "${ADMIN_PASSWORD}" \
    --mariadb-user-host-login-scope='%'
fi

# One app at a time, not five --install-app flags on new-site. Batched, the
# after_install hooks interleave and erpnext's own fixtures are not all in place
# when its company setup creates the Transit warehouse, so the whole thing dies
# on `LinkValidationError: Could not find Warehouse Type: Transit` — a record
# from erpnext's own setup, with nothing in the error naming the real cause.
for app in erpnext payments hrms education ags_edusmart; do
  if bench --site "${SITE}" list-apps 2>/dev/null | grep -qx "${app}"; then
    echo "[test-site-init] ${app} already installed"
  else
    echo "[test-site-init] installing ${app}"
    bench --site "${SITE}" install-app "${app}"
  fi
done

echo "[test-site-init] done"
bench --site "${SITE}" list-apps
