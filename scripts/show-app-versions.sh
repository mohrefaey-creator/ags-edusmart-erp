#!/usr/bin/env bash
# What is actually inside the built image: every Frappe app, its version, and
# the branch and commit it was built from.
#
#   sudo bash scripts/show-app-versions.sh [tag]
#
# The Dockerfile pins branches rather than floating tags, so this is how you
# check what a given image really contains — an ERP that reprices fees
# differently after an unattended rebuild is worse than one a month behind.
set -uo pipefail

TAG=${1:-ags/edusmart-erp:local}

docker image inspect "${TAG}" >/dev/null 2>&1 || {
  echo "image ${TAG} not found" >&2; exit 1; }

docker run --rm --entrypoint /bin/bash "${TAG}" -c '
cd /home/frappe/frappe-bench
printf "%-14s %-10s %-14s %-10s %s\n" APP VERSION BRANCH COMMIT DATE
for a in $(ls apps); do
  v=$(python -c "import ${a}; print(getattr(${a}, \"__version__\", \"?\"))" 2>/dev/null || echo "?")
  if [ -d "apps/${a}/.git" ]; then
    b=$(git -C "apps/${a}" rev-parse --abbrev-ref HEAD 2>/dev/null)
    c=$(git -C "apps/${a}" rev-parse --short HEAD 2>/dev/null)
    d=$(git -C "apps/${a}" log -1 --format=%cs 2>/dev/null)
  else
    b="(not a clone)"; c="-"; d="-"
  fi
  printf "%-14s %-10s %-14s %-10s %s\n" "${a}" "${v}" "${b}" "${c}" "${d}"
done
'
