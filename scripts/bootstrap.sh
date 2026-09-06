#!/usr/bin/env bash
# Build the AGS EduSmart stack from nothing.
#
# Installs the system dependencies, initialises a bench, fetches every app at
# the commit pinned in apps.json, creates a site and installs the AGS layer.
#
#   bash scripts/bootstrap.sh                        # default site ags.localhost
#   bash scripts/bootstrap.sh --site staging.localhost
#   bash scripts/bootstrap.sh --skip-system          # deps already present
#
# Idempotent: every step checks before acting, so a re-run after a failure picks
# up where it stopped rather than starting over.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BENCH_DIR=${BENCH_DIR:-/home/frappe/frappe-bench}
BENCH_USER=${BENCH_USER:-frappe}
SITE=${SITE:-ags.localhost}
# Local development placeholders. Production supplies these from the secret
# manager - see infra/k8s/00-namespace-config.yaml.
DB_ROOT_PASSWORD=${DB_ROOT_PASSWORD:-dev-not-a-real-credential}
ADMIN_PASSWORD=${ADMIN_PASSWORD:-dev-admin-not-real}
SKIP_SYSTEM=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --site) SITE="$2"; shift 2 ;;
    --bench) BENCH_DIR="$2"; shift 2 ;;
    --skip-system) SKIP_SYSTEM=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

say()  { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[33m    %s\033[0m\n' "$1"; }
die()  { printf '\033[31m    FATAL: %s\033[0m\n' "$1" >&2; exit 1; }

# ---------------------------------------------------------------- system deps
if [[ ${SKIP_SYSTEM} -eq 0 ]]; then
  say "System dependencies"
  if [[ $(id -u) -ne 0 ]]; then
    warn "not root; skipping apt. Re-run with sudo or pass --skip-system."
  else
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq --no-install-recommends \
      git curl ca-certificates build-essential \
      python3 python3-dev python3-venv python3-pip \
      mariadb-server mariadb-client libmariadb-dev \
      redis-server \
      libssl-dev libffi-dev libxml2-dev libxslt1-dev zlib1g-dev pkg-config \
      wkhtmltopdf xfonts-75dpi xfonts-base \
      fonts-noto fonts-noto-core \
      >/dev/null
    echo "    installed"

    # Frappe requires utf8mb4. Anything narrower silently truncates Arabic names
    # and corrupts the byte-length count in the ZATCA seller-name TLV.
    if [[ ! -f /etc/mysql/mariadb.conf.d/99-frappe.cnf ]]; then
      install -d /etc/mysql/mariadb.conf.d
      cp "${REPO_ROOT}/infra/mariadb/primary.cnf" \
         /etc/mysql/mariadb.conf.d/99-frappe.cnf 2>/dev/null || true
      echo "    MariaDB tuned from infra/mariadb/primary.cnf"
    fi

    id -u "${BENCH_USER}" >/dev/null 2>&1 || useradd -ms /bin/bash "${BENCH_USER}"
  fi
fi

# -------------------------------------------------------------------- services
say "Services"
if ! mariadb -uroot -p"${DB_ROOT_PASSWORD}" -e "SELECT 1" >/dev/null 2>&1; then
  service mariadb start >/dev/null 2>&1 || true
  sleep 3
  # On a fresh MariaDB root authenticates over the socket and has no password;
  # after the first run it has one, so the socket route is refused. Handle both.
  if mariadb -e "SELECT 1" >/dev/null 2>&1; then
    mariadb -e "ALTER USER 'root'@'localhost' IDENTIFIED VIA mysql_native_password \
      USING PASSWORD('${DB_ROOT_PASSWORD}'); FLUSH PRIVILEGES;"
    echo "    root password set"
  elif mariadb -uroot -p"${DB_ROOT_PASSWORD}" -e "SELECT 1" >/dev/null 2>&1; then
    echo "    root already has the expected password"
  else
    die "cannot authenticate to MariaDB as root either way. If this machine had
    MariaDB before, its root password is not the one this script expects."
  fi
else
  echo "    MariaDB up"
fi

# Ports match sites/common_site_config.json, not the Redis defaults.
for port in 11000 13000; do
  redis-cli -p "${port}" ping >/dev/null 2>&1 \
    || redis-server --port "${port}" --daemonize yes >/dev/null 2>&1
done
sysctl -w vm.overcommit_memory=1 >/dev/null 2>&1 || true
echo "    Redis up on 11000 / 13000"

# ------------------------------------------------------------------ the bench
say "Bench"
run_as_bench() { su - "${BENCH_USER}" -c "$1"; }
[[ $(id -un) == "${BENCH_USER}" ]] && run_as_bench() { bash -lc "$1"; }

if [[ ! -d "${BENCH_DIR}/apps/frappe" ]]; then
  FRAPPE_BRANCH=$(python3 -c "
import json,sys
apps=json.load(open('${REPO_ROOT}/apps.json'))
print(next((a['branch'] for a in apps if a['url'].endswith('/frappe')), 'version-16'))
" 2>/dev/null || echo version-16)
  run_as_bench "pip install --user --quiet frappe-bench && \
    export PATH=\$HOME/.local/bin:\$PATH && \
    bench init --frappe-branch ${FRAPPE_BRANCH} --skip-redis-config-generation \
      ${BENCH_DIR}"
  echo "    bench initialised"
else
  echo "    bench already exists at ${BENCH_DIR}"
fi

# ------------------------------------------------------------------- the apps
say "Apps (pinned by apps.json)"
python3 - "${REPO_ROOT}/apps.json" > /tmp/ags-apps.txt <<'PY'
import json, sys
for app in json.load(open(sys.argv[1])):
    name = app["url"].rstrip("/").split("/")[-1]
    print(f"{name}\t{app['url']}\t{app['branch']}\t{app.get('commit') or ''}")
PY

while IFS=$'\t' read -r name url branch commit; do
  if [[ -d "${BENCH_DIR}/apps/${name}" ]]; then
    echo "    ${name} already present"
    continue
  fi
  # The AGS app is this repo's sibling; prefer the local checkout so a
  # developer's uncommitted work is what gets installed.
  if [[ "${name}" == "ags_edusmart" && -d "${REPO_ROOT}/apps/ags_edusmart" ]]; then
    run_as_bench "cd ${BENCH_DIR} && export PATH=\$HOME/.local/bin:\$PATH && \
      bench get-app '${REPO_ROOT}/apps/ags_edusmart'" \
      || die "could not install the local ags_edusmart checkout"
    echo "    ags_edusmart installed from ${REPO_ROOT}/apps/ags_edusmart"
    continue
  fi
  run_as_bench "cd ${BENCH_DIR} && export PATH=\$HOME/.local/bin:\$PATH && \
    bench get-app --branch ${branch} --resolve-deps ${url}" \
    || die "could not fetch ${name}"
  if [[ -n "${commit}" ]]; then
    run_as_bench "cd ${BENCH_DIR}/apps/${name} && git fetch --depth 50 origin ${commit} \
      && git checkout --quiet ${commit}" \
      || warn "${name}: could not pin to ${commit} (shallow clone?); left on ${branch}"
  fi
  echo "    ${name} installed"
done < /tmp/ags-apps.txt

# ------------------------------------------------------------------- the site
say "Site ${SITE}"
if [[ -d "${BENCH_DIR}/sites/${SITE}" ]]; then
  echo "    already exists"
else
  run_as_bench "cd ${BENCH_DIR} && export PATH=\$HOME/.local/bin:\$PATH && \
    bench new-site ${SITE} \
      --db-root-password '${DB_ROOT_PASSWORD}' \
      --admin-password '${ADMIN_PASSWORD}' \
      --install-app erpnext --install-app payments \
      --install-app hrms --install-app education \
      --set-default" || die "site creation failed"

  # A bench new-site site has none of the setup-wizard fixtures, and Frappe
  # Education's Fee Category auto-creates an Item that needs them (Warehouse
  # Type, UOMs, item groups). Without this the first fee category fails.
  run_as_bench "cd ${BENCH_DIR} && export PATH=\$HOME/.local/bin:\$PATH && \
    bench --site ${SITE} execute \
      erpnext.setup.setup_wizard.operations.install_fixtures.install \
      --kwargs '{\"country\": \"Saudi Arabia\"}'" \
    || warn "ERPNext fixtures did not install cleanly; check before creating fee categories"

  run_as_bench "cd ${BENCH_DIR} && export PATH=\$HOME/.local/bin:\$PATH && \
    bench --site ${SITE} install-app ags_edusmart" || die "ags_edusmart install failed"
  echo "    created and installed"
fi

say "Migrate"
run_as_bench "cd ${BENCH_DIR} && export PATH=\$HOME/.local/bin:\$PATH && \
  bench --site ${SITE} migrate" >/dev/null || die "migrate failed"
echo "    schema up to date"

say "Done"
cat <<INFO
  Bench   ${BENCH_DIR}
  Site    ${SITE}

  Next:
    bash scripts/start-dev.sh                       # serve on :8000
    bench --site ${SITE} execute ags_edusmart.setup.demo.build
    bench --site ${SITE} run-tests --app ags_edusmart
INFO
