#!/usr/bin/env bash
# Bring the AGS EduSmart development stack up inside WSL.
#
# WSL shuts the distro down when it goes idle, which stops MariaDB and Redis and
# clears /tmp. So this is written to be run repeatedly: every step checks before
# it acts, and running it on an already-healthy stack is a no-op.
#
#   wsl -d Ubuntu-26.04 -u root -- bash /mnt/c/.../scripts/start-dev.sh
set -uo pipefail

BENCH=/home/frappe/frappe-bench
SITE=${SITE:-ags.localhost}
DB_ROOT_PASSWORD=${DB_ROOT_PASSWORD:-dev-not-a-real-credential}

say() { printf '\n\033[1m%s\033[0m\n' "$1"; }

say "MariaDB"
if mariadb -uroot -p"${DB_ROOT_PASSWORD}" -e "SELECT 1" >/dev/null 2>&1; then
  echo "  already running"
else
  service mariadb start >/dev/null 2>&1
  for _ in $(seq 1 30); do
    mariadb -uroot -p"${DB_ROOT_PASSWORD}" -e "SELECT 1" >/dev/null 2>&1 && break
    sleep 1
  done
  mariadb -uroot -p"${DB_ROOT_PASSWORD}" -e "SELECT 1" >/dev/null 2>&1 \
    && echo "  started" || { echo "  FAILED to start MariaDB"; exit 1; }
fi

say "Redis"
# Frappe expects three logical instances; the ports match
# sites/common_site_config.json, not the Redis defaults.
for port in 11000 13000; do
  if redis-cli -p "${port}" ping >/dev/null 2>&1; then
    echo "  ${port} already running"
  else
    redis-server --port "${port}" --daemonize yes >/dev/null 2>&1
    sleep 1
    redis-cli -p "${port}" ping >/dev/null 2>&1 \
      && echo "  ${port} started" || echo "  ${port} FAILED"
  fi
done

# Redis warns loudly (and can fail a background save) without this.
sysctl -w vm.overcommit_memory=1 >/dev/null 2>&1 || true

say "Bench"
if curl -sf -m 5 http://localhost:8000/api/method/ping >/dev/null 2>&1; then
  echo "  already serving on :8000"
else
  su - frappe -c "cd ${BENCH} && export PATH=\$HOME/.local/bin:\$PATH && \
    nohup bench --site ${SITE} serve --port 8000 > /tmp/serve.log 2>&1 &"
  for _ in $(seq 1 45); do
    curl -sf -m 5 http://localhost:8000/api/method/ping >/dev/null 2>&1 && break
    sleep 2
  done
  if curl -sf -m 5 http://localhost:8000/api/method/ping >/dev/null 2>&1; then
    echo "  serving on :8000"
  else
    echo "  FAILED to start; last lines of /tmp/serve.log:"
    tail -20 /tmp/serve.log
    exit 1
  fi
fi

say "Ready"
cat <<INFO
  Desk           http://localhost:8000/app        (Administrator)
  Parent portal  http://localhost:8000/parent
  Site           ${SITE}

  Smoke check:   bash scripts/smoke-portal.sh
INFO
