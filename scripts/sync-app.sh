#!/usr/bin/env bash
# Copy the ags_edusmart source from the Windows repo into the WSL bench.
#
# The repo is the source of truth; the bench holds a working copy. A symlink
# across /mnt/c is fragile for Frappe's file watcher and importlib, and an
# in-place bench edit would drift from the repo - so this is a one-way sync.
set -euo pipefail

REPO_APP="/mnt/c/Users/malrefaey/Desktop/Apps/School ERP/apps/ags_edusmart"
BENCH="${BENCH:-/home/frappe/frappe-bench}"
TARGET="${BENCH}/apps/ags_edusmart"

if [[ ! -d "${REPO_APP}" ]]; then
  echo "source app not found: ${REPO_APP}" >&2
  exit 1
fi

mkdir -p "${TARGET}"
rsync -a --delete \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.git' \
  --exclude 'node_modules' --exclude '*.egg-info' \
  "${REPO_APP}/" "${TARGET}/"

# Register the app with the bench environment the first time round.
if ! "${BENCH}/env/bin/python" -c "import ags_edusmart" >/dev/null 2>&1; then
  "${BENCH}/env/bin/pip" install --quiet -e "${TARGET}"
fi

grep -qx "ags_edusmart" "${BENCH}/sites/apps.txt" 2>/dev/null \
  || echo "ags_edusmart" >> "${BENCH}/sites/apps.txt"

echo "synced ags_edusmart -> ${TARGET}"
