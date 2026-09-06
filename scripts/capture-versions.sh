#!/usr/bin/env bash
# Emit the exact upstream commit every app is pinned to.
#
# The output is committed as docs/versions.lock.md. An ERP that reprices fees
# differently after an unattended `bench update` is worse than one that is a
# month behind, so the deployment repo records what it was built against rather
# than trusting a branch name.
set -uo pipefail

BENCH=${BENCH:-/home/frappe/frappe-bench}
APPS=${APPS:-"frappe erpnext hrms education payments"}

cd "${BENCH}" || { echo "no bench at ${BENCH}" >&2; exit 1; }

printf '%-12s %-42s %-12s %s\n' APP COMMIT BRANCH REMOTE
for app in ${APPS}; do
  dir="${BENCH}/apps/${app}"
  [ -d "${dir}/.git" ] || continue
  commit=$(git --git-dir="${dir}/.git" --work-tree="${dir}" rev-parse HEAD 2>/dev/null)
  branch=$(git --git-dir="${dir}/.git" --work-tree="${dir}" rev-parse --abbrev-ref HEAD 2>/dev/null)
  remote=$(git --git-dir="${dir}/.git" --work-tree="${dir}" remote get-url origin 2>/dev/null)
  version=$(python3 - "$dir" "$app" <<'PY' 2>/dev/null
import os, re, sys
base, app = sys.argv[1], sys.argv[2]
init = os.path.join(base, app, "__init__.py")
try:
    text = open(init, encoding="utf-8").read()
except OSError:
    print(""); raise SystemExit
m = re.search(r'__version__\s*=\s*["\']([^"\']+)', text)
print(m.group(1) if m else "")
PY
)
  printf '%-12s %-42s %-12s %s\n' "${app}" "${commit}" "${branch:-detached}" "${remote}"
  printf '%-12s version %s\n' "" "${version}"
done
